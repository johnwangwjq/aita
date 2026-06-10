from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import click
from click.exceptions import UsageError

from aita import exit_codes
from aita.config import build_test_specs
from aita.config import get_suite_hooks
from aita.config import load_dotenv
from aita.config import load_suite_config
from aita.config import load_test_documents
from aita.config import require_global_config
from aita.deterministic_assertions import assert_deterministic_expectations
from aita.deterministic_assertions import should_run_llm_assertion
from aita.discovery import discover_test_files
from aita.hooks import run_hooks
from aita.http_client import call_endpoint
from aita.http_client import create_runtime_context
from aita.http_client import run_auth_request
from aita.llm_asserter import assert_round
from aita.models import RoundResult
from aita.models import RuntimeContext
from aita.models import TestResult
from aita.models import TestSpec
from aita.report import build_summary
from aita.report import format_summary


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv) if argv is not None else None
    try:
        result = cli.main(args=args, prog_name="aita", standalone_mode=False)
        return int(result)
    except UsageError as exc:
        if exc.__class__.__name__ == "NoArgsIsHelpError" and getattr(exc, "ctx", None) is not None:
            click.echo(exc.ctx.get_help())
            return 0
        click.echo(str(exc), err=True)
        return 2
    except Exception as exc:
        click.echo(str(exc), err=True)
        return 2


@click.command(context_settings={"help_option_names": ["--help"]}, no_args_is_help=True)
@click.argument("paths", nargs=-1, type=click.Path(path_type=Path))
@click.option(
    "--all", "run_all", is_flag=True,
    help="Run all testsuite directories in the current directory")
@click.option("--dry-run", is_flag=True)
@click.option("--max-rounds", type=int, default=None)
@click.option(
    "--timeout", type=int, default=30, show_default=True,
    help="the timeout on all outbound http calls in seconds")
@click.option("--verbose", is_flag=True)
@click.option("--quiet-hooks", is_flag=True, help="Suppress hook output; shown only on failure")
def cli(
    paths: tuple[Path, ...],
    run_all: bool,
    dry_run: bool,
    max_rounds: int | None,
    timeout: int,
    verbose: bool,
    quiet_hooks: bool,
) -> int:
    """Run one or more test files or testsuite directories."""
    return _run_command(
        targets=paths,
        run_all=run_all,
        dry_run=dry_run,
        max_rounds=max_rounds,
        timeout=timeout,
        verbose=verbose,
        quiet_hooks=quiet_hooks,
    )


def _run_command(
    targets: Sequence[Path],
    run_all: bool,
    dry_run: bool,
    max_rounds: int | None,
    timeout: int,
    verbose: bool,
    quiet_hooks: bool = False,
) -> int:
    cwd = Path.cwd()
    resolved_targets = _resolve_targets(cwd, targets, run_all)
    project_root = _find_project_root(cwd, resolved_targets)
    load_dotenv(project_root)
    global_config = require_global_config(project_root) if (project_root / "aita.yaml").exists() else {}

    # Build per-target groups: (target, suite_dir, suite_hooks, specs)
    suite_groups: list[tuple[Path, tuple[str, ...], tuple[str, ...], list[TestSpec]]] = []
    seen_test_files: set[Path] = set()
    for target in resolved_targets:
        suite_config = load_suite_config(target)
        suite_pre, suite_post = get_suite_hooks(suite_config, global_config)
        suite_dir = target if target.is_dir() else target.parent
        specs: list[TestSpec] = []
        for test_file in discover_test_files(target):
            test_file_key = test_file.resolve()
            if test_file_key in seen_test_files:
                continue
            seen_test_files.add(test_file_key)
            docs = load_test_documents(test_file)
            specs.extend(build_test_specs(test_file, docs, global_config, suite_config))
        suite_groups.append((suite_dir, suite_pre, suite_post, specs))

    if dry_run:
        total = sum(len(specs) for _, _, _, specs in suite_groups)
        print(f"Validation successful. Tests discovered: {total}")
        return exit_codes.PASS

    results: list[TestResult] = []
    logged_in_context_cache: dict[str, RuntimeContext] = {}
    for suite_dir, suite_pre, suite_post, specs in suite_groups:

        if verbose: print(f'Run testsuite {suite_dir.name}')

        run_hooks(suite_pre, cwd=suite_dir.resolve(), quiet=quiet_hooks)
        try:
            for spec in specs:

                if verbose: print(f'Testing {spec.name}')

                runtime_context: RuntimeContext | None = None
                perform_login_bootstrap = True

                if spec.identity.login_required:
                    cache_key = _build_logged_in_cache_key(spec)
                    runtime_context = logged_in_context_cache.get(cache_key)
                    if runtime_context is None:
                        runtime_context = create_runtime_context("logged-in")
                        if spec.identity.authentication is None:
                            raise ValueError("authentication is required when login-required is true")
                        run_auth_request(
                            endpoint=spec.endpoint,
                            auth_request=spec.identity.authentication,
                            timeout=timeout,
                            context=runtime_context,
                            verbose=verbose,
                        )
                        logged_in_context_cache[cache_key] = runtime_context
                    perform_login_bootstrap = False

                results.append(
                    _run_single_test(
                        spec,
                        max_rounds=max_rounds,
                        timeout=timeout,
                        verbose=verbose,
                        quiet_hooks=quiet_hooks,
                        runtime_context=runtime_context,
                        perform_login_bootstrap=perform_login_bootstrap,
                    )
                )
        finally:
            run_hooks(suite_post, cwd=suite_dir.resolve(), quiet=quiet_hooks)

    summary = build_summary(results)
    print(format_summary(summary))

    if summary.errored > 0:
        return exit_codes.ERROR
    if summary.failed > 0:
        return exit_codes.FAIL
    return exit_codes.PASS


def _resolve_targets(cwd: Path, targets: Sequence[Path], run_all: bool) -> tuple[Path, ...]:
    if run_all and targets:
        raise UsageError("Cannot combine --all with explicit paths")

    if run_all:
        suite_dirs = tuple(
            child
            for child in sorted(cwd.iterdir())
            if child.is_dir() and bool(discover_test_files(child))
        )
        if not suite_dirs:
            raise ValueError(f"No testsuite directories found in {cwd}")
        return suite_dirs

    if not targets:
        raise UsageError("Provide one or more paths, or use --all")

    return tuple(targets)


def _find_project_root(cwd: Path, resolved_targets: tuple[Path, ...]) -> Path:
    """Return the directory containing the global aita.yaml.

    Walks up from the parent of the first target to find aita.yaml,
    falling back to cwd.
    """
    anchor = resolved_targets[0].resolve() if resolved_targets else cwd
    # Start from the parent so the target's own aita.yaml (suite config) is not confused
    # with the global project aita.yaml.
    candidate = anchor.parent if anchor.is_dir() else anchor.parent
    while True:
        if (candidate / "aita.yaml").exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return cwd


def _run_single_test(
    spec: TestSpec,
    max_rounds: int | None,
    timeout: int,
    verbose: bool,
    quiet_hooks: bool = False,
    runtime_context: RuntimeContext | None = None,
    perform_login_bootstrap: bool = True,
) -> TestResult:
    rounds_run = 0
    round_results: list[RoundResult] = []
    failure_reason: str | None = None
    errored = False
    if runtime_context is None:
        runtime_context = create_runtime_context("logged-in" if spec.identity.login_required else "anonymous")

    try:
        run_hooks(spec.pre_test, cwd=Path(spec.source_file).resolve().parent, quiet=quiet_hooks)

        if spec.identity.login_required and perform_login_bootstrap:
            if spec.identity.authentication is None:
                raise ValueError("authentication is required when login-required is true")
            run_auth_request(
                endpoint=spec.endpoint,
                auth_request=spec.identity.authentication,
                timeout=timeout,
                context=runtime_context,
                verbose=verbose,
            )

        for index, round_spec in enumerate(spec.rounds, start=1):
            if max_rounds is not None and index > max_rounds:
                if verbose: print(f"  Stop assertion at max round: {max_rounds}")
                break

            if verbose: print(f'  Sending {round_spec.input_text}')
            endpoint_response = call_endpoint(
                endpoint=spec.endpoint,
                input_text=round_spec.input_text,
                timeout=timeout,
                context=runtime_context,
            )
            rounds_run += 1

            if round_spec.expected is None:
                round_results.append(
                    RoundResult(
                        index=index,
                        endpoint_response=endpoint_response.body,
                        assertion_skipped=True,
                        assertion_passed=True,
                        failure_reason=None,
                    )
                )
                continue

            deterministic_ok, deterministic_reason = assert_deterministic_expectations(
                expected=round_spec.expected,
                endpoint_response=endpoint_response,
            )
            if not deterministic_ok:
                failure_reason = deterministic_reason or "Deterministic assertion failed"
                round_results.append(
                    RoundResult(
                        index=index,
                        endpoint_response=endpoint_response.body,
                        assertion_skipped=False,
                        assertion_passed=False,
                        failure_reason=failure_reason,
                    )
                )
                break

            if not should_run_llm_assertion(round_spec.expected):
                if verbose: print(f"    Deterministic passed")
                round_results.append(
                    RoundResult(
                        index=index,
                        endpoint_response=endpoint_response.body,
                        assertion_skipped=True,
                        assertion_passed=True,
                        failure_reason=None,
                    )
                )
                continue

            assertion_passed, assertion_reason = assert_round(
                asserter=spec.asserter,
                input_text=round_spec.input_text,
                endpoint_response=endpoint_response.body,
                expected_response=round_spec.expected.like,
                fail_on=round_spec.expected.fail_on,
                timeout=timeout,
            )

            if verbose: print(f"    LLM {'passed' if assertion_passed else 'failed'}")

            if not assertion_passed:
                failure_reason = assertion_reason or "Assertion failed"
                round_results.append(
                    RoundResult(
                        index=index,
                        endpoint_response=endpoint_response.body,
                        assertion_skipped=False,
                        assertion_passed=False,
                        failure_reason=failure_reason,
                    )
                )
                break

            round_results.append(
                RoundResult(
                    index=index,
                    endpoint_response=endpoint_response.body,
                    assertion_skipped=False,
                    assertion_passed=True,
                    failure_reason=None,
                )
            )
    except Exception as exc:
        errored = True
        failure_reason = str(exc)
    finally:
        run_hooks(spec.post_test, cwd=Path(spec.source_file).resolve().parent, quiet=quiet_hooks)

    passed = not errored and failure_reason is None
    return TestResult(
        test_name=spec.name,
        source_file=spec.source_file,
        source_document_index=spec.source_document_index,
        passed=passed,
        errored=errored,
        error_message=failure_reason,
        rounds_run=rounds_run,
        rounds=tuple(round_results),
    )


def _build_logged_in_cache_key(spec: TestSpec) -> str:
    auth = spec.identity.authentication
    if auth is None:
        raise ValueError("authentication is required when login-required is true")

    payload = {
        "login_required": spec.identity.login_required,
        "endpoint": spec.endpoint,
        "auth_path": auth.path,
        "auth_method": auth.method,
        "auth_headers": auth.headers,
        "auth_body": auth.body,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))

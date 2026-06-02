from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import click
from click.exceptions import NoArgsIsHelpError
from click.exceptions import UsageError

from aita import exit_codes
from aita.config import build_test_specs
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
    except NoArgsIsHelpError as exc:
        click.echo(exc.ctx.get_help())
        return 0
    except UsageError as exc:
        click.echo(str(exc), err=True)
        return 2


@click.group()
def cli() -> None:
    """Aita command-line entrypoint."""


@cli.command("run", help="Run one test file or a testsuite directory")
@click.argument("path", type=click.Path(path_type=Path))
@click.option("--dry-run", is_flag=True)
@click.option("--max-rounds", type=int, default=None)
@click.option("--timeout", type=int, default=30, show_default=True)
@click.option("--verbose", is_flag=True)
def run_command(path: Path, dry_run: bool, max_rounds: int | None, timeout: int, verbose: bool) -> int:
    return _run_command(
        target=path,
        dry_run=dry_run,
        max_rounds=max_rounds,
        timeout=timeout,
        verbose=verbose,
    )


def _run_command(
    target: Path,
    dry_run: bool,
    max_rounds: int | None,
    timeout: int,
    verbose: bool,
) -> int:
    cwd = Path.cwd()
    load_dotenv(cwd)
    global_config = require_global_config(cwd)
    suite_config = load_suite_config(target)

    all_specs: list[TestSpec] = []
    for test_file in discover_test_files(target):
        docs = load_test_documents(test_file)
        all_specs.extend(build_test_specs(test_file, docs, global_config, suite_config))

    if dry_run:
        print(f"Validation successful. Tests discovered: {len(all_specs)}")
        return exit_codes.PASS

    results: list[TestResult] = []
    logged_in_context_cache: dict[str, RuntimeContext] = {}
    for spec in all_specs:
        runtime_context: RuntimeContext | None = None
        perform_login_bootstrap = True

        if spec.identity.mode == "logged-in":
            cache_key = _build_logged_in_cache_key(spec)
            runtime_context = logged_in_context_cache.get(cache_key)
            if runtime_context is None:
                runtime_context = create_runtime_context(spec.identity.mode)
                if spec.identity.auth_request is None:
                    raise ValueError("identity.auth-request is required when identity.mode is logged-in")
                run_auth_request(
                    auth_request=spec.identity.auth_request,
                    timeout=timeout,
                    context=runtime_context,
                )
                logged_in_context_cache[cache_key] = runtime_context
            perform_login_bootstrap = False

        results.append(
            _run_single_test(
                spec,
                max_rounds=max_rounds,
                timeout=timeout,
                verbose=verbose,
                runtime_context=runtime_context,
                perform_login_bootstrap=perform_login_bootstrap,
            )
        )

    summary = build_summary(results)
    print(format_summary(summary))

    if summary.errored > 0:
        return exit_codes.ERROR
    if summary.failed > 0:
        return exit_codes.FAIL
    return exit_codes.PASS


def _run_single_test(
    spec: TestSpec,
    max_rounds: int | None,
    timeout: int,
    verbose: bool,
    runtime_context: RuntimeContext | None = None,
    perform_login_bootstrap: bool = True,
) -> TestResult:
    rounds_run = 0
    round_results: list[RoundResult] = []
    failure_reason: str | None = None
    errored = False
    if runtime_context is None:
        runtime_context = create_runtime_context(spec.identity.mode)

    try:
        run_hooks(spec.pre_test, cwd=Path.cwd())

        if spec.identity.mode == "logged-in" and perform_login_bootstrap:
            if spec.identity.auth_request is None:
                raise ValueError("identity.auth-request is required when identity.mode is logged-in")
            run_auth_request(
                auth_request=spec.identity.auth_request,
                timeout=timeout,
                context=runtime_context,
            )

        for index, round_spec in enumerate(spec.rounds, start=1):
            if max_rounds is not None and index > max_rounds:
                break

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
                if verbose:
                    print(f"[{spec.name}] round {index}: deterministic assertions passed")
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
                expected_response=round_spec.expected.response,
                fail_on=round_spec.expected.fail_on,
                timeout=timeout,
            )

            if verbose:
                print(f"[{spec.name}] round {index}: assertion={assertion_passed}")

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
        run_hooks(spec.post_test, cwd=Path.cwd())

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
    auth = spec.identity.auth_request
    if auth is None:
        raise ValueError("identity.auth-request is required when identity.mode is logged-in")

    payload = {
        "mode": spec.identity.mode,
        "endpoint": spec.endpoint,
        "auth_endpoint": auth.endpoint,
        "auth_method": auth.method,
        "auth_headers": auth.headers,
        "auth_body": auth.body,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))

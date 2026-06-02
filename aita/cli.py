from __future__ import annotations

from pathlib import Path
from typing import Sequence

import click

from aita import exit_codes
from aita.config import build_test_specs
from aita.config import load_suite_config
from aita.config import load_test_documents
from aita.config import require_global_config
from aita.discovery import discover_test_files
from aita.hooks import run_hooks
from aita.http_client import call_endpoint
from aita.llm_asserter import assert_round
from aita.models import RoundResult
from aita.models import TestResult
from aita.models import TestSpec
from aita.report import build_summary
from aita.report import format_summary


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv) if argv is not None else None
    result = cli.main(args=args, prog_name="aita", standalone_mode=False)
    return int(result)


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
    for spec in all_specs:
        results.append(_run_single_test(spec, max_rounds=max_rounds, timeout=timeout, verbose=verbose))

    summary = build_summary(results)
    print(format_summary(summary))

    if summary.errored > 0:
        return exit_codes.ERROR
    if summary.failed > 0:
        return exit_codes.FAIL
    return exit_codes.PASS


def _run_single_test(spec: TestSpec, max_rounds: int | None, timeout: int, verbose: bool) -> TestResult:
    rounds_run = 0
    round_results: list[RoundResult] = []
    failure_reason: str | None = None
    errored = False

    try:
        run_hooks(spec.pre_test, cwd=Path.cwd())

        for index, round_spec in enumerate(spec.rounds, start=1):
            if max_rounds is not None and index > max_rounds:
                break

            endpoint_response = call_endpoint(spec.endpoint, round_spec.input_text, timeout=timeout)
            rounds_run += 1

            if round_spec.expected is None:
                round_results.append(
                    RoundResult(
                        index=index,
                        endpoint_response=endpoint_response,
                        assertion_skipped=True,
                        assertion_passed=True,
                        failure_reason=None,
                    )
                )
                continue

            assertion_passed, assertion_reason = assert_round(
                asserter=spec.asserter,
                input_text=round_spec.input_text,
                endpoint_response=endpoint_response,
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
                        endpoint_response=endpoint_response,
                        assertion_skipped=False,
                        assertion_passed=False,
                        failure_reason=failure_reason,
                    )
                )
                break

            round_results.append(
                RoundResult(
                    index=index,
                    endpoint_response=endpoint_response,
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

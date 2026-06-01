from __future__ import annotations

from aita.models import RunSummary
from aita.models import TestResult


def build_summary(results: list[TestResult]) -> RunSummary:
    total = len(results)
    passed = sum(1 for item in results if item.passed)
    failed = sum(1 for item in results if not item.passed and not item.errored)
    errored = sum(1 for item in results if item.errored)
    skipped_assertions = sum(
        1 for item in results for round_result in item.rounds if round_result.assertion_skipped
    )
    return RunSummary(
        total=total,
        passed=passed,
        failed=failed,
        errored=errored,
        skipped_assertions=skipped_assertions,
        tests=tuple(results),
    )


def format_summary(summary: RunSummary) -> str:
    lines = [
        f"Total tests: {summary.total}",
        f"Passed: {summary.passed}",
        f"Failed: {summary.failed}",
        f"Errored: {summary.errored}",
        f"Skipped assertions: {summary.skipped_assertions}",
    ]

    for result in summary.tests:
        status = "PASSED" if result.passed else ("ERRORED" if result.errored else "FAILED")
        lines.append(
            f"- [{status}] {result.test_name} ({result.source_file}#{result.source_document_index})"
        )
        if result.error_message:
            lines.append(f"  reason: {result.error_message}")

    return "\n".join(lines)

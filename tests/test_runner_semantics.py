from __future__ import annotations

import unittest
from unittest.mock import patch

from aita.cli import _run_single_test
from aita.models import AsserterConfig
from aita.models import RoundExpected
from aita.models import RoundSpec
from aita.models import TestSpec


class RunnerSemanticsTests(unittest.TestCase):
    def test_expected_absent_skips_asserter(self) -> None:
        spec = TestSpec(
            name="x",
            endpoint="http://e",
            asserter=AsserterConfig(url="http://a", api_key="k", invoke_options={}),
            pre_test=(),
            post_test=(),
            rounds=(RoundSpec(input_text="hi", expected=None),),
            source_file="case.yaml",
            source_document_index=1,
        )

        with patch("aita.cli.call_endpoint", return_value="ok") as endpoint_mock:
            with patch("aita.cli.assert_round") as asserter_mock:
                result = _run_single_test(spec, max_rounds=None, timeout=5, verbose=False)

        self.assertTrue(result.passed)
        self.assertEqual(result.rounds_run, 1)
        self.assertEqual(endpoint_mock.call_count, 1)
        self.assertEqual(asserter_mock.call_count, 0)

    def test_fail_fast_within_test(self) -> None:
        spec = TestSpec(
            name="x",
            endpoint="http://e",
            asserter=AsserterConfig(url="http://a", api_key="k", invoke_options={}),
            pre_test=(),
            post_test=(),
            rounds=(
                RoundSpec(input_text="r1", expected=RoundExpected(response="x", fail_on="bad")),
                RoundSpec(input_text="r2", expected=RoundExpected(response="x", fail_on="bad")),
            ),
            source_file="case.yaml",
            source_document_index=1,
        )

        with patch("aita.cli.call_endpoint", return_value="ok") as endpoint_mock:
            with patch("aita.cli.assert_round", return_value=(False, "failed")):
                result = _run_single_test(spec, max_rounds=None, timeout=5, verbose=False)

        self.assertFalse(result.passed)
        self.assertEqual(result.rounds_run, 1)
        self.assertEqual(endpoint_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()

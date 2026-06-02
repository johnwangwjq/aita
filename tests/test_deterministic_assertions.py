from __future__ import annotations

import unittest

from aita.deterministic_assertions import assert_deterministic_expectations
from aita.deterministic_assertions import should_run_llm_assertion
from aita.models import EndpointResponse
from aita.models import RoundExpected


class DeterministicAssertionsTests(unittest.TestCase):
    def test_status_code_and_kind_pass(self) -> None:
        expected = RoundExpected(
            response="hint",
            fail_on="bad",
            status_code=200,
            status_kind="ok",
            has_session_id=False,
            metadata_has=("actions",),
        )
        endpoint_response = EndpointResponse(
            body='{"status":{"kind":"ok"},"metadata":{"actions":[]}}',
            status_code=200,
            headers={},
        )

        passed, reason = assert_deterministic_expectations(expected, endpoint_response)
        self.assertTrue(passed)
        self.assertIsNone(reason)

    def test_status_code_mismatch_fails(self) -> None:
        expected = RoundExpected(
            response=None,
            fail_on=None,
            status_code=200,
            status_kind=None,
            has_session_id=None,
            metadata_has=(),
        )
        endpoint_response = EndpointResponse(body="{}", status_code=500, headers={})

        passed, reason = assert_deterministic_expectations(expected, endpoint_response)
        self.assertFalse(passed)
        self.assertIn("Expected status code", reason or "")

    def test_should_run_llm_assertion(self) -> None:
        expected = RoundExpected(
            response=None,
            fail_on=None,
            status_code=200,
            status_kind=None,
            has_session_id=None,
            metadata_has=(),
        )
        self.assertFalse(should_run_llm_assertion(expected))


if __name__ == "__main__":
    unittest.main()

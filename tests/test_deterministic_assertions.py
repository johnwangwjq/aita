from __future__ import annotations

import unittest

from aita.deterministic_assertions import assert_deterministic_expectations
from aita.deterministic_assertions import should_run_llm_assertion
from aita.models import EndpointResponse
from aita.models import RoundExpected


class DeterministicAssertionsTests(unittest.TestCase):
    def test_status_code_and_kind_pass(self) -> None:
        expected = RoundExpected(
            like="hint",
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
            like=None,
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

    def test_metadata_has_nested_key_exists(self) -> None:
        expected = RoundExpected(
            like=None,
            fail_on=None,
            status_code=200,
            status_kind="ok",
            has_session_id=None,
            metadata_has=("server-routing.intent",),
        )
        endpoint_response = EndpointResponse(
            body='{"status":{"kind":"ok"},"metadata":{"server-routing":{"intent":"plan"}}}',
            status_code=200,
            headers={},
        )
        passed, reason = assert_deterministic_expectations(expected, endpoint_response)
        self.assertTrue(passed)
        self.assertIsNone(reason)

    def test_metadata_has_nested_key_missing_fails(self) -> None:
        expected = RoundExpected(
            like=None,
            fail_on=None,
            status_code=200,
            status_kind="ok",
            has_session_id=None,
            metadata_has=("server-routing.intent",),
        )
        endpoint_response = EndpointResponse(
            body='{"status":{"kind":"ok"},"metadata":{"server-routing":{}}}',
            status_code=200,
            headers={},
        )
        passed, reason = assert_deterministic_expectations(expected, endpoint_response)
        self.assertFalse(passed)
        self.assertIn("server-routing.intent", reason or "")

    def test_metadata_has_nested_value_match(self) -> None:
        expected = RoundExpected(
            like=None,
            fail_on=None,
            status_code=200,
            status_kind="ok",
            has_session_id=None,
            metadata_has=("server-routing.intent=general",),
        )
        endpoint_response = EndpointResponse(
            body='{"status":{"kind":"ok"},"metadata":{"server-routing":{"intent":"general","classifier-op":"create"}}}',
            status_code=200,
            headers={},
        )
        passed, reason = assert_deterministic_expectations(expected, endpoint_response)
        self.assertTrue(passed)
        self.assertIsNone(reason)

    def test_metadata_has_nested_value_mismatch_fails(self) -> None:
        expected = RoundExpected(
            like=None,
            fail_on=None,
            status_code=200,
            status_kind="ok",
            has_session_id=None,
            metadata_has=("server-routing.intent=general",),
        )
        endpoint_response = EndpointResponse(
            body='{"status":{"kind":"ok"},"metadata":{"server-routing":{"intent":"plan"}}}',
            status_code=200,
            headers={},
        )
        passed, reason = assert_deterministic_expectations(expected, endpoint_response)
        self.assertFalse(passed)
        self.assertIn("server-routing.intent", reason or "")
        self.assertIn("general", reason or "")

    def test_should_run_llm_assertion(self) -> None:
        expected = RoundExpected(
            like=None,
            fail_on=None,
            status_code=200,
            status_kind=None,
            has_session_id=None,
            metadata_has=(),
        )
        self.assertFalse(should_run_llm_assertion(expected))


if __name__ == "__main__":
    unittest.main()

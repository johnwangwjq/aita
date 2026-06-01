from __future__ import annotations

import unittest

from aita.llm_asserter import _build_request_payload


class LlmAsserterTests(unittest.TestCase):
    def test_invoke_options_override_defaults(self) -> None:
        payload = _build_request_payload(
            user_prompt="u",
            invoke_options={"model": "custom-model", "temperature": 0.3, "top_p": 0.5},
        )

        self.assertEqual(payload["model"], "custom-model")
        self.assertEqual(payload["temperature"], 0.3)
        self.assertEqual(payload["top_p"], 0.5)
        self.assertEqual(len(payload["messages"]), 2)

    def test_messages_not_overridden_by_options(self) -> None:
        payload = _build_request_payload(
            user_prompt="u",
            invoke_options={"messages": [{"role": "user", "content": "bad"}]},
        )

        self.assertEqual(payload["messages"][1]["content"], "u")


if __name__ == "__main__":
    unittest.main()

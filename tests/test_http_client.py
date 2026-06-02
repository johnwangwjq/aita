from __future__ import annotations

import json
import unittest

from aita.http_client import _build_payload
from aita.http_client import create_runtime_context
from aita.http_client import _update_runtime_context
from aita.models import EndpointResponse


class HttpClientTests(unittest.TestCase):
    def test_anonymous_payload_includes_session_id(self) -> None:
        payload = _build_payload(
            input_text="hello",
            identity_mode="anonymous",
            session_id="sess-1",
        )
        self.assertEqual(payload["message"], "hello")
        self.assertEqual(payload["session_id"], "sess-1")

    def test_context_updates_session_id_from_response(self) -> None:
        context = create_runtime_context("anonymous")
        response = EndpointResponse(
            body=json.dumps({"answer": "ok", "session_id": "sess-2"}),
            status_code=200,
            headers={},
        )

        _update_runtime_context(context, response)
        self.assertEqual(context.session_id, "sess-2")

    def test_legacy_payload_has_no_session_id(self) -> None:
        payload = _build_payload(
            input_text="hello",
            identity_mode="legacy",
            session_id=None,
        )
        self.assertEqual(payload, {"message": "hello"})


if __name__ == "__main__":
    unittest.main()

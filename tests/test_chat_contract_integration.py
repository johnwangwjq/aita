from __future__ import annotations

import json
import threading
import unittest
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer

from aita.cli import _run_single_test
from aita.models import AuthRequestSpec
from aita.models import AsserterConfig
from aita.models import IdentityConfig
from aita.models import RoundExpected
from aita.models import RoundSpec
from aita.models import TestSpec


class _ContractHandler(BaseHTTPRequestHandler):
    server_version = "AitaContractMock/1.0"

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        body = json.loads(raw_body or "{}")

        if self.path == "/api/login":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", "sid=login-123; Path=/")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "answer": "logged in",
                        "metadata": {},
                        "status": {"kind": "ok"},
                    }
                ).encode("utf-8")
            )
            return

        if self.path == "/api/chat":
            cookie = self.headers.get("Cookie", "")
            session_id = body.get("session_id")
            if "sid=login-123" in cookie:
                payload = {
                    "answer": "hello authenticated user",
                    "metadata": {"actions": [{"id": "x", "label": "y", "payload": {}}]},
                    "status": {"kind": "ok"},
                }
            else:
                sid = session_id if isinstance(session_id, str) and session_id else "anon-123"
                payload = {
                    "answer": "hello anonymous user",
                    "metadata": {"actions": []},
                    "status": {"kind": "ok"},
                    "session_id": sid,
                }

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


class ContractIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _ContractHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.chat_endpoint = f"http://{host}:{port}/api/chat"
        self.login_endpoint = f"http://{host}:{port}/api/login"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_anonymous_chat_continuity(self) -> None:
        spec = TestSpec(
            name="anon-flow",
            endpoint=self.chat_endpoint,
            asserter=AsserterConfig(url="http://unused", api_key="unused", invoke_options={}),
            identity=IdentityConfig(login_required=False, authentication=None),
            pre_test=(),
            post_test=(),
            rounds=(
                RoundSpec(
                    input_text="你好",
                    expected=RoundExpected(
                        like=None,
                        fail_on=None,
                        status_code=200,
                        status_kind="ok",
                        has_session_id=True,
                        metadata_has=("actions",),
                    ),
                ),
                RoundSpec(
                    input_text="请继续",
                    expected=RoundExpected(
                        like=None,
                        fail_on=None,
                        status_code=200,
                        status_kind="ok",
                        has_session_id=True,
                        metadata_has=("actions",),
                    ),
                ),
            ),
            source_file="integration.yaml",
            source_document_index=1,
        )

        result = _run_single_test(spec, max_rounds=None, timeout=5, verbose=False)

        self.assertTrue(result.passed)
        self.assertEqual(result.rounds_run, 2)

    def test_logged_in_cookie_flow(self) -> None:
        spec = TestSpec(
            name="logged-flow",
            endpoint=self.chat_endpoint,
            asserter=AsserterConfig(url="http://unused", api_key="unused", invoke_options={}),
            identity=IdentityConfig(
                login_required=True,
                authentication=AuthRequestSpec(
                    path="/api/login",
                    method="POST",
                    headers={"Content-Type": "application/json"},
                    body={"email": "u", "password": "p"},
                ),
            ),
            pre_test=(),
            post_test=(),
            rounds=(
                RoundSpec(
                    input_text="帮我做规划",
                    expected=RoundExpected(
                        like=None,
                        fail_on=None,
                        status_code=200,
                        status_kind="ok",
                        has_session_id=False,
                        metadata_has=("actions",),
                    ),
                ),
            ),
            source_file="integration.yaml",
            source_document_index=1,
        )

        result = _run_single_test(spec, max_rounds=None, timeout=5, verbose=False)

        self.assertTrue(result.passed)
        self.assertEqual(result.rounds_run, 1)


if __name__ == "__main__":
    unittest.main()

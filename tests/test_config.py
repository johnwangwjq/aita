from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from aita.config import build_test_specs
from aita.config import load_dotenv
from aita.config import load_test_documents
from aita.config import require_global_config


class ConfigTests(unittest.TestCase):
  def test_load_dotenv_populates_missing_env_vars(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      (root / ".env").write_text(
        """
TEST_KEY=dotenv-value
QUOTED='quoted value'
""".strip()
        + "\n",
        encoding="utf-8",
      )

      os.environ.pop("TEST_KEY", None)
      os.environ.pop("QUOTED", None)
      load_dotenv(root)

      self.assertEqual(os.environ["TEST_KEY"], "dotenv-value")
      self.assertEqual(os.environ["QUOTED"], "quoted value")

  def test_load_dotenv_does_not_override_existing_env(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      (root / ".env").write_text("TEST_KEY=dotenv-value\n", encoding="utf-8")

      os.environ["TEST_KEY"] = "already-set"
      load_dotenv(root)

      self.assertEqual(os.environ["TEST_KEY"], "already-set")

    def test_global_config_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cwd = Path(temp_dir)
            with self.assertRaises(ValueError):
                require_global_config(cwd)

    def test_multi_document_and_merge_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            test_file = root / "suite.yaml"
            test_file.write_text(
                """
name: test-one
rounds:
  - input: hello
---
name: test-two
endpoint: http://doc-endpoint
asserter:
  url: http://doc-asserter
  api-key: ${TEST_KEY}
rounds:
  - input: hi
""".strip()
                + "\n",
                encoding="utf-8",
            )

            os.environ["TEST_KEY"] = "k"
            docs = load_test_documents(test_file)
            global_config = {
                "endpoint": "http://global-endpoint",
                "asserter": {"url": "http://global-asserter", "api-key": "global-key"},
                "pre-test": ["echo global-pre"],
                "post-test": ["echo global-post"],
            }
            suite_config = {
                "endpoint": "http://suite-endpoint",
                "asserter": {"url": "http://suite-asserter", "api-key": "suite-key"},
            }

            specs = build_test_specs(test_file, docs, global_config, suite_config)

            self.assertEqual(len(specs), 2)
            self.assertEqual(specs[0].endpoint, "http://suite-endpoint")
            self.assertEqual(specs[0].asserter.url, "http://suite-asserter")
            self.assertEqual(specs[0].pre_test, ("echo global-pre",))
            self.assertEqual(specs[1].endpoint, "http://doc-endpoint")
            self.assertEqual(specs[1].asserter.url, "http://doc-asserter")
            self.assertEqual(specs[1].asserter.api_key, "k")

    def test_asserter_invoke_options_merge_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            test_file = root / "suite.yaml"
            test_file.write_text(
                """
name: merged-asserter-options
asserter:
  invoke-options:
    temperature: 0.7
    max_tokens: 200
rounds:
  - input: hello
""".strip()
                + "\n",
                encoding="utf-8",
            )

            docs = load_test_documents(test_file)
            global_config = {
                "endpoint": "http://global-endpoint",
                "asserter": {
                    "url": "http://global-asserter",
                    "api-key": "global-key",
                    "invoke-options": {
                        "model": "global-model",
                        "temperature": 0,
                        "top_p": 0.9,
                    },
                },
            }
            suite_config = {
                "asserter": {
                    "url": "http://suite-asserter",
                    "api-key": "suite-key",
                    "invoke-options": {
                        "temperature": 0.2,
                        "top_p": 0.8,
                    },
                }
            }

            spec = build_test_specs(test_file, docs, global_config, suite_config)[0]
            self.assertEqual(spec.asserter.url, "http://suite-asserter")
            self.assertEqual(spec.asserter.api_key, "suite-key")
            self.assertEqual(
                spec.asserter.invoke_options,
                {
                    "model": "global-model",
                    "temperature": 0.7,
                    "top_p": 0.8,
                    "max_tokens": 200,
                },
            )

    def test_identity_auth_request_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            test_file = root / "suite.yaml"
            test_file.write_text(
                """
name: auth-chat
identity:
  mode: logged-in
  auth-request:
    endpoint: http://app.local/api/login
    method: POST
    headers:
      Content-Type: application/json
    body:
      username: ${TEST_USER}
      password: ${TEST_PASS}
rounds:
  - input: hi
""".strip()
                + "\n",
                encoding="utf-8",
            )

            os.environ["TEST_USER"] = "john"
            os.environ["TEST_PASS"] = "secret"
            docs = load_test_documents(test_file)
            global_config = {
                "endpoint": "http://app.local/api/chat",
                "asserter": {"url": "http://global-asserter", "api-key": "global-key"},
            }

            spec = build_test_specs(test_file, docs, global_config, {})[0]
            self.assertEqual(spec.identity.mode, "logged-in")
            self.assertEqual(spec.identity.auth_request.endpoint, "http://app.local/api/login")
            self.assertEqual(spec.identity.auth_request.body["username"], "john")

    def test_parses_deterministic_expected_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            test_file = root / "suite.yaml"
            test_file.write_text(
                """
name: deterministic
identity:
  mode: anonymous
rounds:
  - input: hello
    expected:
      status-code: 200
      status-kind: ok
      has-session-id: false
      metadata-has:
        - messages
""".strip()
                + "\n",
                encoding="utf-8",
            )

            docs = load_test_documents(test_file)
            global_config = {
                "endpoint": "http://app.local/api/chat",
                "asserter": {"url": "http://global-asserter", "api-key": "global-key"},
            }

            expected = build_test_specs(test_file, docs, global_config, {})[0].rounds[0].expected
            self.assertEqual(expected.status_code, 200)
            self.assertEqual(expected.status_kind, "ok")
            self.assertFalse(expected.has_session_id)
            self.assertEqual(expected.metadata_has, ("messages",))

    def test_logged_in_requires_auth_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            test_file = root / "suite.yaml"
            test_file.write_text(
                """
name: invalid
identity:
  mode: logged-in
rounds:
  - input: hi
""".strip()
                + "\n",
                encoding="utf-8",
            )

            docs = load_test_documents(test_file)
            global_config = {
                "endpoint": "http://app.local/api/chat",
                "asserter": {"url": "http://global-asserter", "api-key": "global-key"},
            }

            with self.assertRaises(ValueError):
                build_test_specs(test_file, docs, global_config, {})


if __name__ == "__main__":
    unittest.main()

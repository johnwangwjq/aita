from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from aita.config import build_test_specs
from aita.config import load_test_documents
from aita.config import require_global_config


class ConfigTests(unittest.TestCase):
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

    def test_required_keys_name_rounds_and_round_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            test_file = root / "suite.yaml"
            test_file.write_text(
                """
name: x
rounds:
  - input: hello
""".strip()
                + "\n",
                encoding="utf-8",
            )

            docs = load_test_documents(test_file)
            global_config = {
                "endpoint": "http://global-endpoint",
                "asserter": {"url": "http://global-asserter", "api-key": "global-key"},
            }
            suite_config = {}

            specs = build_test_specs(test_file, docs, global_config, suite_config)
            self.assertEqual(len(specs), 1)

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

            specs = build_test_specs(test_file, docs, global_config, suite_config)
            spec = specs[0]

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


if __name__ == "__main__":
    unittest.main()

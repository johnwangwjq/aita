from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aita.cli import main


class CliTests(unittest.TestCase):
    def test_dry_run_directory_suite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "aita.yaml").write_text(
                """
endpoint: http://global-endpoint
asserter:
  url: http://global-asserter
  api-key: ${TEST_KEY}
pre-test: []
post-test: []
""".strip()
                + "\n",
                encoding="utf-8",
            )

            suite = root / "suite"
            suite.mkdir()
            (suite / "case.yaml").write_text(
                """
name: case
rounds:
  - input: hello
""".strip()
                + "\n",
                encoding="utf-8",
            )

            os.environ["TEST_KEY"] = "k"
            with patch("pathlib.Path.cwd", return_value=root):
                code = main([str(suite), "--dry-run"])

            self.assertEqual(code, 0)

    def test_dry_run_multiple_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "aita.yaml").write_text(
                """
endpoint: http://global-endpoint
asserter:
  url: http://global-asserter
  api-key: ${TEST_KEY}
pre-test: []
post-test: []
""".strip()
                + "\n",
                encoding="utf-8",
            )

            foo = root / "foo"
            foo.mkdir()
            (foo / "case.yaml").write_text("name: foo\nrounds:\n  - input: hello\n", encoding="utf-8")

            bar = root / "bar"
            bar.mkdir()
            (bar / "baz.yaml").write_text("name: baz\nrounds:\n  - input: hi\n", encoding="utf-8")

            os.environ["TEST_KEY"] = "k"
            with patch("pathlib.Path.cwd", return_value=root):
                code = main([str(foo), str(bar / "baz.yaml"), "--dry-run"])

            self.assertEqual(code, 0)

    def test_dry_run_all_testsuites_in_current_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "aita.yaml").write_text(
                """
endpoint: http://global-endpoint
asserter:
  url: http://global-asserter
  api-key: ${TEST_KEY}
pre-test: []
post-test: []
""".strip()
                + "\n",
                encoding="utf-8",
            )

            foo = root / "foo"
            foo.mkdir()
            (foo / "case.yaml").write_text("name: foo\nrounds:\n  - input: hello\n", encoding="utf-8")

            bar = root / "bar"
            bar.mkdir()
            (bar / "baz.yaml").write_text("name: baz\nrounds:\n  - input: hi\n", encoding="utf-8")

            os.environ["TEST_KEY"] = "k"
            with patch("pathlib.Path.cwd", return_value=root):
                code = main(["--all", "--dry-run"])

            self.assertEqual(code, 0)

    def test_missing_global_config_returns_error_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite_file = root / "case.yaml"
            suite_file.write_text(
                """
name: case
rounds:
  - input: hello
""".strip()
                + "\n",
                encoding="utf-8",
            )

            with patch("pathlib.Path.cwd", return_value=root):
                code = main([str(suite_file)])

            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call
from unittest.mock import patch

from aita.cli import _find_project_root
from aita.cli import _resolve_targets
from aita.cli import main


class FindProjectRootTests(unittest.TestCase):
    def test_finds_aita_yaml_in_target_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "aita.yaml").write_text("", encoding="utf-8")
            suite = root / "suite"
            suite.mkdir()
            # suite has its own aita.yaml — should NOT be returned, root should be
            (suite / "aita.yaml").write_text("", encoding="utf-8")
            self.assertEqual(_find_project_root(root, (suite,)), root)

    def test_walks_up_to_find_aita_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "aita.yaml").write_text("", encoding="utf-8")
            suite = root / "a" / "b"
            suite.mkdir(parents=True)
            self.assertEqual(_find_project_root(root, (suite,)), root)

    def test_falls_back_to_cwd_when_no_aita_yaml_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cwd = Path(temp_dir)
            suite = cwd / "suite"
            suite.mkdir()
            self.assertEqual(_find_project_root(cwd, (suite,)), cwd)

    def test_dotenv_loaded_from_project_root_not_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "aita.yaml").write_text(
                "endpoint: http://e\nasserter:\n  url: http://a\n  api-key: k\n",
                encoding="utf-8",
            )
            (root / ".env").write_text("DOTENV_ROOT_VAR=from-root\n", encoding="utf-8")

            suite = root / "suite"
            suite.mkdir()
            # launch cwd is different from project root
            launch_cwd = Path(temp_dir) / "elsewhere"
            launch_cwd.mkdir()
            (launch_cwd / ".env").write_text("DOTENV_ROOT_VAR=from-cwd\n", encoding="utf-8")
            (suite / "case.yaml").write_text(
                "name: x\nrounds:\n  - input: hi\n", encoding="utf-8"
            )

            os.environ.pop("DOTENV_ROOT_VAR", None)
            with patch("pathlib.Path.cwd", return_value=launch_cwd):
                main([str(suite), "--dry-run"])

            self.assertEqual(os.environ.get("DOTENV_ROOT_VAR"), "from-root")
            os.environ.pop("DOTENV_ROOT_VAR", None)


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

    def test_dry_run_all_ignores_dirs_with_leading_dash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            good = root / "suite"
            good.mkdir()
            (good / "case.yaml").write_text("name: good\nrounds:\n  - input: hi\n", encoding="utf-8")

            ignored = root / "-disabled"
            ignored.mkdir()
            (ignored / "case.yaml").write_text("name: bad\nrounds:\n  - input: hi\n", encoding="utf-8")

            targets = _resolve_targets(root, (), run_all=True)

            self.assertIn(good.resolve(), targets)
            self.assertNotIn(ignored.resolve(), targets)

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

    def test_suite_hooks_run_once_per_test_hooks_run_per_test(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "aita.yaml").write_text(
                "endpoint: http://e\nasserter:\n  url: http://a\n  api-key: k\n",
                encoding="utf-8",
            )
            suite = root / "suite"
            suite.mkdir()
            (suite / "aita.yaml").write_text(
                "pre-test:\n  - echo suite-pre\npost-test:\n  - echo suite-post\n",
                encoding="utf-8",
            )
            (suite / "t1.yaml").write_text(
                "name: t1\npre-test:\n  - echo per-test-pre\nrounds:\n  - input: hi\n",
                encoding="utf-8",
            )
            (suite / "t2.yaml").write_text(
                "name: t2\nrounds:\n  - input: hi\n",
                encoding="utf-8",
            )

            os.environ.setdefault("TEST_KEY", "k")
            with patch("pathlib.Path.cwd", return_value=root):
                with patch("aita.cli.run_hooks") as hooks_mock:
                    with patch("aita.cli.call_endpoint") as ep_mock:
                        ep_mock.return_value.body = "ok"
                        ep_mock.return_value.status_code = 200
                        ep_mock.return_value.headers = {}
                        main([str(suite)])

            suite_dir = suite.resolve()
            # Suite hooks called exactly once each (wrapping both tests)
            hooks_mock.assert_any_call(("echo suite-pre",), cwd=suite_dir, quiet=False)
            hooks_mock.assert_any_call(("echo suite-post",), cwd=suite_dir, quiet=False)
            suite_pre_calls = [c for c in hooks_mock.call_args_list if c == call(("echo suite-pre",), cwd=suite_dir, quiet=False)]
            suite_post_calls = [c for c in hooks_mock.call_args_list if c == call(("echo suite-post",), cwd=suite_dir, quiet=False)]
            self.assertEqual(len(suite_pre_calls), 1)
            self.assertEqual(len(suite_post_calls), 1)
            # Per-test hook for t1 called once (only t1 defines it)
            t1_cwd = (suite / "t1.yaml").resolve().parent
            per_test_pre_calls = [c for c in hooks_mock.call_args_list if c == call(("echo per-test-pre",), cwd=t1_cwd, quiet=False)]
            self.assertEqual(len(per_test_pre_calls), 1)


if __name__ == "__main__":
    unittest.main()

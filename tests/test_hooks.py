from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from aita.hooks import run_hooks


class HooksTests(unittest.TestCase):
    def test_quiet_false_passes_output_to_console(self) -> None:
        # When quiet=False, subprocess.run is called without stdout/stderr redirection.
        # We verify by ensuring a successful command doesn't raise.
        run_hooks(("echo hello",), cwd=Path("."), quiet=False)

    def test_quiet_true_suppresses_output_on_success(self) -> None:
        # No output should reach the console; no exception raised.
        run_hooks(("echo hello",), cwd=Path("."), quiet=True)

    def test_quiet_true_raises_on_failure_with_output(self) -> None:
        with self.assertRaises(subprocess.CalledProcessError) as ctx:
            run_hooks(("echo boom && exit 1",), cwd=Path("."), quiet=True)
        self.assertIn("boom", ctx.exception.output)

    def test_quiet_false_raises_on_failure(self) -> None:
        with self.assertRaises(subprocess.CalledProcessError):
            run_hooks(("exit 1",), cwd=Path("."), quiet=False)

    def test_empty_hooks_does_nothing(self) -> None:
        run_hooks((), cwd=Path("."), quiet=True)
        run_hooks((), cwd=Path("."), quiet=False)


if __name__ == "__main__":
    unittest.main()

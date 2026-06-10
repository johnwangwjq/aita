from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def run_hooks(hooks: tuple[str, ...], cwd: Path, quiet: bool = False) -> None:
    for command in hooks:
        if not quiet:
            subprocess.run(command, shell=True, cwd=str(cwd), check=True)
            continue

        with tempfile.TemporaryFile(mode="w+", suffix=".log") as log:
            result = subprocess.run(
                command, shell=True, cwd=str(cwd),
                stdout=log, stderr=log,
            )
            if result.returncode != 0:
                log.seek(0)
                output = log.read()
                raise subprocess.CalledProcessError(
                    result.returncode, command, output=output
                )

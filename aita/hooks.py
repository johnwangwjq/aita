from __future__ import annotations

import subprocess
from pathlib import Path


def run_hooks(hooks: tuple[str, ...], cwd: Path) -> None:
    for command in hooks:
        subprocess.run(command, shell=True, cwd=str(cwd), check=True)

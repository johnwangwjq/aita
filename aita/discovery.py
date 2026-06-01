from __future__ import annotations

from pathlib import Path


def discover_test_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]

    if not path.is_dir():
        raise ValueError(f"Path does not exist: {path}")

    files = [
        child
        for child in sorted(path.iterdir())
        if child.is_file()
        and child.name != "aita.yaml"
        and child.suffix.lower() in {".yaml", ".yml"}
    ]
    return files

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aita.discovery import discover_test_files


class DiscoveryTests(unittest.TestCase):
    def test_discovers_top_level_yaml_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "aita.yaml").write_text("x: 1\n", encoding="utf-8")
            (root / "a.yaml").write_text("name: a\n", encoding="utf-8")
            (root / "b.yml").write_text("name: b\n", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "c.yaml").write_text("name: c\n", encoding="utf-8")

            found = discover_test_files(root)

            self.assertEqual([item.name for item in found], ["a.yaml", "b.yml"])


if __name__ == "__main__":
    unittest.main()

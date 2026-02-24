from __future__ import annotations

import unittest
from pathlib import Path

from app.mid_catalog import MidCatalog


class CatalogTests(unittest.TestCase):
    def test_catalog_loads_and_has_expected_mids(self) -> None:
        path = Path(__file__).resolve().parent.parent / "data" / "mid_catalog.json"
        catalog = MidCatalog.from_file(path)
        self.assertGreaterEqual(catalog.len(), 191)
        for mid in ("0001", "0002", "0061", "0900", "2500", "9999"):
            self.assertTrue(catalog.contains(mid), mid)


if __name__ == "__main__":
    unittest.main()


from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from backend.indexer import inventory_snapshot, synchronize


FIXTURES = Path(__file__).resolve().parent / "fixtures"


class IndexerTests(TestCase):
    def test_catalog_is_base_and_unknown_files_are_ignored(self) -> None:
        with TemporaryDirectory() as cache:
            with patch("backend.indexer.CACHE_DIR", Path(cache)):
                result = synchronize("raw", str(FIXTURES / "raw"), recursive=False)

        stations = {station["code"]: station for station in result["data"]}
        self.assertEqual(43, len(stations))
        self.assertEqual(1, result["fileCount"])
        self.assertEqual(1, result["ignoredFileCount"])
        self.assertEqual("2026-01-01", stations["LIM_ChicoSoldados"]["start"])
        self.assertEqual("", stations["LIM_Yanuncay-AJ-Tarqui"]["start"])

    def test_recursive_mode_and_incremental_cache(self) -> None:
        with TemporaryDirectory() as cache:
            with patch("backend.indexer.CACHE_DIR", Path(cache)):
                first = synchronize("raw", str(FIXTURES / "raw"), recursive=True)
                second = synchronize("raw", str(FIXTURES / "raw"), recursive=True)

        self.assertEqual(1, first["fileCount"])
        self.assertEqual(2, first["ignoredFileCount"])
        self.assertEqual(1, first["sync"]["processed"])
        self.assertEqual(0, second["sync"]["processed"])
        self.assertEqual(1, second["sync"]["reused"])

    def test_snapshot_returns_catalog_and_last_inventory_without_scanning_source(self) -> None:
        with TemporaryDirectory() as cache:
            with patch("backend.indexer.CACHE_DIR", Path(cache)):
                synchronize("raw", str(FIXTURES / "raw"), recursive=True)
                result = inventory_snapshot("raw")

        stations = {station["code"]: station for station in result["data"]}
        self.assertTrue(result["snapshot"])
        self.assertEqual(43, len(stations))
        self.assertEqual(1, result["fileCount"])
        self.assertEqual("2026-01-01", stations["LIM_ChicoSoldados"]["start"])

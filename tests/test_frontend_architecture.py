from pathlib import Path
import re
from unittest import TestCase

from backend.user_data import DATA_MODULES


ROOT = Path(__file__).resolve().parents[1]


class FrontendArchitectureTests(TestCase):
    def test_global_responsive_sheet_contains_only_shared_layout_rules(self) -> None:
        responsive = (ROOT / "frontend/css/responsive.css").read_text(encoding="utf-8")

        for feature_prefix in (".agenda-", ".hydromet-", ".settings-"):
            self.assertNotIn(feature_prefix, responsive)

    def test_feature_responsive_rules_live_with_their_modules(self) -> None:
        agenda = (ROOT / "frontend/css/agenda.css").read_text(encoding="utf-8")
        hydromet = (ROOT / "frontend/css/hydromet.css").read_text(encoding="utf-8")
        settings = (ROOT / "frontend/css/settings.css").read_text(encoding="utf-8")

        self.assertIn("@media (max-width: 900px)", agenda)
        self.assertIn("@media (max-width: 900px)", hydromet)
        self.assertIn("@media (max-width: 1250px)", settings)

    def test_viewer_api_delegates_duckdb_queries_to_domain_module(self) -> None:
        api = (ROOT / "backend/viewer/api.py").read_text(encoding="utf-8")
        queries = (ROOT / "backend/viewer/queries.py").read_text(encoding="utf-8")

        self.assertNotIn("import duckdb", api)
        self.assertIn("from .queries import build_export_query, execute_query, query_data", api)
        self.assertIn("import duckdb", queries)

    def test_application_startup_recovers_from_individual_asset_failures(self) -> None:
        application = (ROOT / "frontend/js/app.js").read_text(encoding="utf-8")
        storage = (ROOT / "frontend/js/core/storage.js").read_text(encoding="utf-8")

        self.assertIn("recoverMissingCoreScripts", application)
        self.assertIn("Promise.allSettled(moduleLoads)", application)
        self.assertIn("cacheBusted(source)", application)
        self.assertIn("window.NotasSettings?.initSettings()", application)
        self.assertIn("No fue posible iniciar Agender.", application)
        self.assertIn("Promise.allSettled(migrations)", storage)

    def test_frontend_storage_keys_match_the_backend_contract(self) -> None:
        storage = (ROOT / "frontend/js/core/storage.js").read_text(encoding="utf-8")
        supported_block = re.search(r"const supportedKeys = \[(.*?)\];", storage, re.DOTALL)

        self.assertIsNotNone(supported_block)
        frontend_keys = set(re.findall(r'"([^"]+)"', supported_block.group(1)))
        self.assertEqual(frontend_keys, set(DATA_MODULES))

import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from openpyxl import load_workbook

from backend.hydromet_export import export_inventory_excel


class HydrometInventoryExportTests(TestCase):
    def test_export_builds_excel_and_neutralizes_formulas(self) -> None:
        with TemporaryDirectory() as root:
            output = Path(root) / "inventario.xlsx"
            with patch("backend.hydromet_export.choose_save_file", return_value=output):
                result = export_inventory_excel(
                    ["Código", "Observación"],
                    [["EST001", "=HYPERLINK(\"https://example.com\")"]],
                    "Inventario 2026",
                )
            workbook = load_workbook(io.BytesIO(output.read_bytes()), read_only=True)
            rows = list(workbook.active.values)

        self.assertTrue(result["saved"])
        self.assertEqual(("Código", "Observación"), rows[0])
        self.assertTrue(rows[1][1].startswith("'="))

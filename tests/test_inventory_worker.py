from __future__ import annotations

import json
from subprocess import CompletedProcess
from unittest import TestCase
from unittest.mock import patch

from backend.main import _synchronize_inventory


class InventoryWorkerTests(TestCase):
    def test_inventory_worker_forces_utf8_and_decodes_json(self) -> None:
        payload = {"stations": [{"name": "Estación Machángara"}]}
        completed = CompletedProcess([], 0, json.dumps(payload, ensure_ascii=False).encode("utf-8"), b"")

        with patch("backend.main.subprocess.run", return_value=completed) as run:
            result = _synchronize_inventory("raw", r"C:\Datos\Año", True)

        self.assertEqual(payload, result)
        self.assertEqual("utf-8", run.call_args.kwargs["env"]["PYTHONIOENCODING"])
        self.assertNotIn("text", run.call_args.kwargs)
        self.assertNotIn("encoding", run.call_args.kwargs)

    def test_inventory_worker_rejects_empty_output(self) -> None:
        completed = CompletedProcess([], 0, b"", b"")

        with patch("backend.main.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(ValueError, "no devolvió datos"):
                _synchronize_inventory("quality", r"C:\Datos", False)

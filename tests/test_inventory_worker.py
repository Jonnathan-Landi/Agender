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

    def test_frozen_inventory_worker_starts_with_a_fresh_pyinstaller_environment(self) -> None:
        completed = CompletedProcess([], 0, b'{"data":[]}', b"")
        with (
            patch("backend.main.sys.frozen", True, create=True),
            patch("backend.main.sys.executable", r"C:\Agender\agender-backend.exe"),
            patch("backend.main.subprocess.run", return_value=completed) as run,
        ):
            _synchronize_inventory("raw", r"C:\Datos", True)

        self.assertEqual("1", run.call_args.kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"])
        self.assertEqual(r"C:\Agender\agender-backend.exe", run.call_args.args[0][0])

    def test_inventory_worker_rejects_empty_output(self) -> None:
        completed = CompletedProcess([], 0, b"", b"")

        with patch("backend.main.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(ValueError, "no devolvió datos"):
                _synchronize_inventory("quality", r"C:\Datos", False)

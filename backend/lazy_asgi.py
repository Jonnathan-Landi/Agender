from __future__ import annotations

import importlib
import threading
from typing import Any


class LazyAsgiApp:
    """Carga una aplicación ASGI pesada únicamente con la primera solicitud."""

    def __init__(self, module_name: str, attribute: str) -> None:
        self.module_name = module_name
        self.attribute = attribute
        self._app: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        if self._app is not None:
            return self._app
        with self._lock:
            if self._app is None:
                module = importlib.import_module(self.module_name)
                self._app = getattr(module, self.attribute)
        return self._app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        await self._load()(scope, receive, send)

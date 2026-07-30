from __future__ import annotations

from copy import deepcopy
import threading
from typing import Any


class JobRegistry:
    """Registro en memoria con copias defensivas y acceso sincronizado."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def add(self, job_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._jobs[job_id] = deepcopy(payload)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return deepcopy(job) if job else None

    def update(self, job_id: str, **values: Any) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.update(values)
            return True

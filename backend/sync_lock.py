from __future__ import annotations

import threading

_guard = threading.Lock()
_locks: dict[int, threading.RLock] = {}


def user_sync_lock(user_id: int) -> threading.RLock:
    with _guard:
        return _locks.setdefault(user_id, threading.RLock())

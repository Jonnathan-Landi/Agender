from __future__ import annotations

import hashlib
from typing import Any


def cloud_profile_id(user: dict[str, Any]) -> str:
    """Stable, non-readable identity for one Agender user inside a cloud account."""
    username = str(user.get("username") or "").strip().casefold()
    return hashlib.sha256(username.encode("utf-8")).hexdigest()[:24]


def cloud_profile_filename(prefix: str, user: dict[str, Any]) -> str:
    return f"{prefix}-{cloud_profile_id(user)}.json"

from __future__ import annotations

from typing import Any

from .config import read_settings, write_settings

PROFILE_PREFERENCES_KEY = "agender.profile.preferences"
PROFILE_SOURCES_KEY = "agender.profile.onedrive-sources"
PROFILE_KEYS = frozenset({PROFILE_PREFERENCES_KEY, PROFILE_SOURCES_KEY})
MAX_PROFILE_BYTES = 32 * 1024


def portable_onedrive_sources(settings: dict[str, Any], current: Any = None) -> dict[str, Any]:
    """Return a compact profile without ever copying device-local paths."""
    result = dict(current) if isinstance(current, dict) else {}
    for source in ("raw", "quality"):
        if settings.get(f"{source}DataSource") != "onedrive":
            continue
        url = str(settings.get(f"{source}OneDriveUrl") or "").strip()
        if not url:
            continue
        result[source] = {
            "url": url,
            "subfolders": bool(settings.get(f"{source}IncludeSubfolders", True)),
        }
    return result


def apply_portable_onedrive_sources(user: dict[str, Any], value: Any) -> bool:
    """Apply shared links while preserving every PC's explicit local configuration."""
    if not isinstance(value, dict):
        return False
    settings = read_settings(user["username"], user.get("role") == "admin")
    changed = False
    for source in ("raw", "quality"):
        shared = value.get(source)
        if not isinstance(shared, dict):
            continue
        url = str(shared.get("url") or "").strip()
        if not url:
            continue
        # A configured local folder is a device override and must never be replaced.
        if settings.get(f"{source}DataSource") == "local" and settings.get(f"{source}DataPath"):
            continue
        updates = {
            f"{source}DataSource": "onedrive",
            f"{source}OneDriveUrl": url,
            f"{source}IncludeSubfolders": bool(shared.get("subfolders", True)),
        }
        for key, item in updates.items():
            if settings.get(key) != item:
                settings[key] = item
                changed = True
    if changed:
        write_settings(settings, user["username"], user.get("role") == "admin")
    return changed

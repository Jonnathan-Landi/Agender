from __future__ import annotations


def clean_name(name: str) -> str:
    cleaned = name.strip().strip('"').strip("'").lower()
    for char in (" ", "-", ".", "/", "\\", ":"):
        cleaned = cleaned.replace(char, "_")
    return cleaned


def canonical_name(name: str) -> str:
    return "".join(char for char in clean_name(name) if char.isalnum())

from __future__ import annotations

from .naming import clean_name


RESOLUTION_INTERVALS = {
    "5min": ("5 minutes", 5 * 60 * 1_000_000),
    "hour": ("1 hour", 60 * 60 * 1_000_000),
    "day": ("1 day", 24 * 60 * 60 * 1_000_000),
    "month": ("1 month", None),
    "year": ("1 year", None),
}


def aggregation_function(variable: str) -> tuple[str, str]:
    """Devuelve la función SQL y su etiqueta según la convención de la variable."""
    canonical = clean_name(variable)
    if canonical.endswith("_min") or canonical == "min":
        return "MIN", "mínimo"
    if canonical.endswith("_max") or canonical == "max":
        return "MAX", "máximo"
    if any(token in canonical for token in ("lluvia", "precip", "rain", "ppt")):
        return "SUM", "suma"
    return "AVG", "promedio"

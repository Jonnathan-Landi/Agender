from __future__ import annotations

import ast
import operator
import re
from pathlib import Path
from typing import Any

from .catalog import normalize_station_code
from .viewer.naming import canonical_name


DISCHARGE_CURVES_FILE = Path(__file__).resolve().parent / "data" / "discharge_curves.yml"
_NUMBER = r"(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?"
_CURVE_LINE = re.compile(rf"^\s*-\s*({_NUMBER}\s*\*\s*\(\s*nivel\s*-\s*{_NUMBER}\s*\)\s*\^\s*{_NUMBER})\s*$", re.I)


def load_discharge_curves(path: Path | None = None) -> dict[str, str]:
    """Carga el subconjunto sencillo del YAML usado para las curvas de descarga."""
    path = path or DISCHARGE_CURVES_FILE
    curves: dict[str, str] = {}
    station: str | None = None
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return curves
    for line_number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line[:1].isspace() and stripped.endswith(":"):
            station = stripped[:-1].strip()
            if not station:
                raise ValueError(f"Estación vacía en {path.name}:{line_number}")
            continue
        match = _CURVE_LINE.fullmatch(line)
        if station and match:
            curves[normalize_station_code(station)] = match.group(1)
            station = None
            continue
        raise ValueError(f"Curva no válida en {path.name}:{line_number}")
    return curves


def curve_for_station(station_code: str | None) -> str | None:
    if not station_code:
        return None
    return load_discharge_curves().get(normalize_station_code(station_code))


def virtual_discharge_variables(
    columns: list[str], station_code: str | None, source: str
) -> dict[str, dict[str, str]]:
    """Describe columnas Q virtuales; nunca modifica ni materializa el dataset."""
    curve = curve_for_station(station_code)
    if not curve:
        return {}
    by_name = {canonical_name(column): column for column in columns}
    wanted = {"Q_Avg": "levelavg"}
    if source == "raw":
        wanted = {"Q_Min": "levelmin", "Q_Max": "levelmax", **wanted}
    return {
        output: {"level_column": by_name[level], "curve": curve}
        for output, level in wanted.items()
        if level in by_name
    }


def variable_sql(variable: str, meta: dict[str, Any]) -> str:
    virtual = meta.get("virtual_variables", {}).get(variable)
    if not virtual:
        return _quote(variable)
    level = _quote(virtual["level_column"])
    return _curve_to_sql(virtual["curve"], level)


def discharge_from_level(expression: str, level: float | int | None) -> float | None:
    """Evalúa una curva validada para un nivel, sin materializar columnas."""
    if level is None:
        return None
    tree = ast.parse(expression.replace("^", "**"), mode="eval")
    binary = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
    }

    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Name) and node.id.casefold() == "nivel":
            return float(level)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and type(node.op) in binary:
            return binary[type(node.op)](evaluate(node.left), evaluate(node.right))
        raise ValueError("Curva de descarga no válida")

    try:
        result = evaluate(tree)
        return result if isinstance(result, float) and result >= 0 else None
    except (ArithmeticError, TypeError, ValueError):
        return None


def _curve_to_sql(expression: str, level_sql: str) -> str:
    tree = ast.parse(expression.replace("^", "**"), mode="eval")

    def render(node: ast.AST) -> str:
        if isinstance(node, ast.Expression):
            return render(node.body)
        if isinstance(node, ast.Name) and node.id.casefold() == "nivel":
            return level_sql
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return repr(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            sign = "+" if isinstance(node.op, ast.UAdd) else "-"
            return f"({sign}{render(node.operand)})"
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            operator = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}[type(node.op)]
            return f"({render(node.left)} {operator} {render(node.right)})"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            return f"POWER({render(node.left)}, {render(node.right)})"
        raise ValueError("La curva solo puede contener nivel, números y operaciones aritméticas")

    return render(tree)


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, BinaryIO


def write_result(result: dict[str, Any], output: BinaryIO | None = None) -> None:
    """Write worker JSON as UTF-8 regardless of the Windows console code page."""
    stream = output or sys.stdout.buffer
    payload = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    stream.write(payload + b"\n")
    stream.flush()


def run(arguments: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Indexador aislado de Agender")
    parser.add_argument("--source", choices=("raw", "quality"), required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--recursive", choices=("true", "false"), default="true")
    values = parser.parse_args(arguments)

    from .indexer import synchronize

    result = synchronize(values.source, values.root, values.recursive == "true")
    write_result(result)


if __name__ == "__main__":
    run()

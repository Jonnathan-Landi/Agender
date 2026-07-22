from __future__ import annotations

import argparse
import json


def run(arguments: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Indexador aislado de Agender")
    parser.add_argument("--source", choices=("raw", "quality"), required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--recursive", choices=("true", "false"), default="true")
    values = parser.parse_args(arguments)

    from .indexer import synchronize

    result = synchronize(values.source, values.root, values.recursive == "true")
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    run()

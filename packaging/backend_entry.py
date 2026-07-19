from __future__ import annotations

import argparse

from backend.main import app
from backend.server import run_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Backend local de Agender")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=47831, type=int)
    arguments = parser.parse_args()
    run_server(app, host=arguments.host, port=arguments.port)


if __name__ == "__main__":
    main()

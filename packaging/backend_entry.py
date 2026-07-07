from __future__ import annotations

import argparse

import uvicorn

from backend.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Backend local de Agender")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", required=True, type=int)
    arguments = parser.parse_args()
    uvicorn.run(
        app,
        host=arguments.host,
        port=arguments.port,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Backend local de Agender")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=47831, type=int)
    parser.add_argument("--index-worker", action="store_true")
    parser.add_argument("--source", choices=("raw", "quality"))
    parser.add_argument("--root")
    parser.add_argument("--recursive", choices=("true", "false"), default="true")
    arguments = parser.parse_args()
    if arguments.index_worker:
        from backend.index_worker import run

        run(
            [
                "--source",
                arguments.source or "raw",
                "--root",
                arguments.root or "",
                "--recursive",
                arguments.recursive,
            ]
        )
        return

    from backend.main import app
    from backend.server import run_server

    run_server(app, host=arguments.host, port=arguments.port)


if __name__ == "__main__":
    main()

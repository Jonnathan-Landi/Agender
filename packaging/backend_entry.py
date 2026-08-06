from __future__ import annotations

import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(description="Backend local de Agender")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=47831, type=int)
    parser.add_argument("--index-worker", action="store_true")
    parser.add_argument("--render-smoke-test", action="store_true")
    parser.add_argument("--climatology-smoke-test", action="store_true")
    parser.add_argument("--source", choices=("raw", "quality"))
    parser.add_argument("--root")
    parser.add_argument("--recursive", choices=("true", "false"), default="true")
    arguments = parser.parse_args()
    if arguments.climatology_smoke_test:
        from backend.climatology_renderer import ASSET_ROOT

        required = ("report.css", "rain_report.css")
        assets = {name: (ASSET_ROOT / name).is_file() for name in required}
        print(json.dumps({"ok": all(assets.values()), "assets": assets}))
        return
    if arguments.render_smoke_test:
        from backend.browser_render import render_smoke_test

        print(json.dumps(render_smoke_test()))
        return
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

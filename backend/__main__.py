import argparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=47831)
    parser.add_argument("--index-worker", action="store_true")
    parser.add_argument("--source", choices=("raw", "quality"))
    parser.add_argument("--root")
    parser.add_argument("--recursive", choices=("true", "false"), default="true")
    args = parser.parse_args()
    if args.index_worker:
        from backend.index_worker import run

        run(["--source", args.source or "raw", "--root", args.root or "", "--recursive", args.recursive])
        return

    from backend.main import app
    from backend.server import run_server

    run_server(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

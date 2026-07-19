import argparse

from backend.main import app
from backend.server import run_server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=47831)
    args = parser.parse_args()
    run_server(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

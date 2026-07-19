from __future__ import annotations

import socket
from collections.abc import Callable

import uvicorn

PORT_ANNOUNCEMENT_PREFIX = "AGENDER_BACKEND_PORT="


def create_server_socket(
    host: str,
    port: int = 0,
    *,
    fallback_to_ephemeral: bool = False,
) -> socket.socket:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        server_socket.bind((host, port))
        server_socket.listen(2048)
        return server_socket
    except OSError:
        server_socket.close()
        if port and fallback_to_ephemeral:
            return create_server_socket(host)
        raise


def run_server(
    app: object,
    host: str = "127.0.0.1",
    port: int = 0,
    announce: Callable[[str], None] = print,
) -> None:
    server_socket = create_server_socket(host, port, fallback_to_ephemeral=True)
    try:
        assigned_port = server_socket.getsockname()[1]
        announce(f"{PORT_ANNOUNCEMENT_PREFIX}{assigned_port}", flush=True)

        config = uvicorn.Config(
            app,
            log_level="warning",
            access_log=False,
        )
        uvicorn.Server(config).run(sockets=[server_socket])
    finally:
        server_socket.close()

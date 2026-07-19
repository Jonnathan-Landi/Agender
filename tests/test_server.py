from __future__ import annotations

import unittest

from backend.server import create_server_socket


class ServerSocketTests(unittest.TestCase):
    def test_ephemeral_ports_are_distinct_and_remain_reserved(self) -> None:
        first = create_server_socket("127.0.0.1")
        second = create_server_socket("127.0.0.1")
        try:
            first_port = first.getsockname()[1]
            second_port = second.getsockname()[1]
            self.assertNotEqual(first_port, second_port)

            with self.assertRaises(OSError):
                create_server_socket("127.0.0.1", first_port)
        finally:
            first.close()
            second.close()

    def test_occupied_preferred_port_falls_back_without_a_race(self) -> None:
        preferred = create_server_socket("127.0.0.1")
        fallback = create_server_socket(
            "127.0.0.1",
            preferred.getsockname()[1],
            fallback_to_ephemeral=True,
        )
        try:
            self.assertNotEqual(
                preferred.getsockname()[1],
                fallback.getsockname()[1],
            )
        finally:
            preferred.close()
            fallback.close()


if __name__ == "__main__":
    unittest.main()

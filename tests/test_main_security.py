from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from starlette.requests import Request
from starlette.responses import Response

from backend.main import RequestSizeLimitMiddleware, cloud_auth_callback


def callback_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "server": ("127.0.0.1", 47831),
            "path": "/api/cloud/auth/callback/onedrive",
            "query_string": b"",
            "headers": [],
        }
    )


class RequestLimitTests(IsolatedAsyncioTestCase):
    async def test_streamed_body_over_limit_is_rejected(self) -> None:
        async def application(scope, receive, send):
            await receive()
            await Response("procesada")(scope, receive, send)

        middleware = RequestSizeLimitMiddleware(application, max_bytes=1)
        incoming = [{"type": "http.request", "body": b"{}", "more_body": False}]
        outgoing = []

        async def receive():
            return incoming.pop(0)

        async def send(message):
            outgoing.append(message)

        await middleware({"type": "http"}, receive, send)
        start = next(message for message in outgoing if message["type"] == "http.response.start")
        self.assertEqual(413, start["status"])


class CallbackEscapingTests(TestCase):
    def test_cloud_callback_escapes_account_content(self) -> None:
        with patch("backend.main.finish_auth", return_value='<img src=x onerror="alert(1)">'):
            response = cloud_auth_callback("onedrive", callback_request())
        content = response.body.decode()
        self.assertEqual(200, response.status_code)
        self.assertNotIn("<img", content)
        self.assertIn("&lt;img", content)

    def test_cloud_callback_escapes_error_content(self) -> None:
        with patch("backend.main.finish_auth", side_effect=ValueError("<script>alert(1)</script>")):
            response = cloud_auth_callback("onedrive", callback_request())
        content = response.body.decode()
        self.assertEqual(400, response.status_code)
        self.assertNotIn("<script>", content)
        self.assertIn("&lt;script&gt;", content)

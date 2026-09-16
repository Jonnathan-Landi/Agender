import asyncio

from starlette.requests import Request
from starlette.responses import Response

from backend.main import enforce_module_access


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("127.0.0.1", 8000),
        }
    )


def test_successful_basemap_response_uses_immutable_cache_without_header_error(monkeypatch):
    monkeypatch.setattr(
        "backend.main.current_user",
        lambda _token: {"modules": ["radar-caxx"]},
    )

    async def call_next(_request):
        return Response(
            b"jpeg",
            status_code=200,
            media_type="image/jpeg",
            headers={"Pragma": "no-cache", "Expires": "0"},
        )

    response = asyncio.run(enforce_module_access(_request("/api/radar-caxx/basemap.jpg"), call_next))

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=604800, immutable"
    assert "pragma" not in response.headers
    assert "expires" not in response.headers


def test_failed_basemap_response_is_never_cached(monkeypatch):
    monkeypatch.setattr(
        "backend.main.current_user",
        lambda _token: {"modules": ["radar-caxx"]},
    )

    async def call_next(_request):
        return Response(b"error", status_code=502)

    response = asyncio.run(enforce_module_access(_request("/api/radar-caxx/basemap.jpg"), call_next))

    assert response.headers["cache-control"].startswith("no-store")

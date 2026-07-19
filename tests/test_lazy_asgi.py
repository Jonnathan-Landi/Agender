import sys
from types import ModuleType
from unittest import IsolatedAsyncioTestCase

from backend.lazy_asgi import LazyAsgiApp


class LazyAsgiTests(IsolatedAsyncioTestCase):
    async def test_application_is_loaded_only_on_first_request(self) -> None:
        module_name = "tests._fake_lazy_asgi"
        module = ModuleType(module_name)
        calls: list[str] = []

        async def fake_app(scope, receive, send):
            calls.append(scope["path"])

        module.app = fake_app
        sys.modules[module_name] = module
        lazy_app = LazyAsgiApp(module_name, "app")
        self.assertIsNone(lazy_app._app)

        try:
            await lazy_app({"type": "http", "path": "/first"}, None, None)
            await lazy_app({"type": "http", "path": "/second"}, None, None)
        finally:
            sys.modules.pop(module_name, None)

        self.assertIs(lazy_app._app, fake_app)
        self.assertEqual(["/first", "/second"], calls)

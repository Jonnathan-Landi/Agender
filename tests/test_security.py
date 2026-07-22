import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from argon2 import PasswordHasher
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend import security


class LicenseRevisionTests(TestCase):
    def test_legacy_report_permission_expands_to_both_submodules(self):
        modules = security._expand_module_access(["reports"])
        self.assertIn("report-water-quality", modules)
        self.assertIn("report-hydromet-network", modules)

    def test_report_submodule_does_not_grant_the_other_report(self):
        modules = security._expand_module_access(["report-water-quality"])
        self.assertIn("reports", modules)
        self.assertIn("report-water-quality", modules)
        self.assertNotIn("report-hydromet-network", modules)

    def test_activation_rejects_same_or_older_revision(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            private_key = Ed25519PrivateKey.generate()
            public_key_path = root / "license_public_key.pem"
            public_key_path.write_bytes(
                private_key.public_key().public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )
            patches = (
                patch.object(security, "APP_DATA_DIR", root),
                patch.object(security, "DB_PATH", root / "users.db"),
                patch.object(security, "LICENSE_PATHS", (root / "license.json",)),
                patch.object(security, "PUBLIC_KEY_PATH", public_key_path),
            )
            for active_patch in patches:
                active_patch.start()
                self.addCleanup(active_patch.stop)

            revision_one = self._license(private_key, 1)
            security.install_license(revision_one, "cliente", "clave-temporal-segura")

            with self.assertRaisesRegex(ValueError, "revisión debe ser superior a 1"):
                security.install_license(revision_one, "cliente", "clave-temporal-segura")

            revision_two = self._license(private_key, 2)
            security.install_license(revision_two, "cliente", "clave-temporal-segura")

            with security.database() as connection:
                row = connection.execute(
                    "SELECT license_revision FROM users WHERE username='cliente'"
                ).fetchone()
            self.assertEqual(2, row["license_revision"])

            session = security.login("cliente", "clave-temporal-segura")
            self.assertIsNotNone(session)
            token, _ = session
            (root / "license.json").write_text("{}", encoding="utf-8")
            self.assertIsNone(security.current_user(token))

    def test_same_user_can_activate_a_new_signed_license_id(self) -> None:
        with TemporaryDirectory() as directory:
            _, private_key = self._configure_security(directory)
            security.install_license(
                self._license(private_key, 4, "ANALISTA-PC-ANTERIOR"),
                "cliente",
                "clave-temporal-segura",
            )

            replacement = self._license(private_key, 1, "ANALISTA-MULTIDISPOSITIVO")
            security.install_license(replacement, "cliente", "clave-temporal-segura")

            with security.database() as connection:
                row = connection.execute(
                    "SELECT license_id,license_revision FROM users WHERE username='cliente'"
                ).fetchone()
            self.assertEqual("ANALISTA-MULTIDISPOSITIVO", row["license_id"])
            self.assertEqual(1, row["license_revision"])

    def test_logged_in_user_can_replace_license_from_another_computer(self) -> None:
        with TemporaryDirectory() as directory:
            _, private_key = self._configure_security(directory)
            security.install_license(
                self._license(private_key, 2, "ANALISTA-PC-1"),
                "cliente",
                "clave-temporal-segura",
            )
            token, _ = security.login("cliente", "clave-temporal-segura")

            user = security.replace_license(
                self._license(private_key, 1, "ANALISTA-COMPARTIDA"),
                token,
            )

            self.assertEqual("cliente", user["username"])
            with security.database() as connection:
                row = connection.execute(
                    "SELECT license_id,license_revision FROM users WHERE username='cliente'"
                ).fetchone()
            self.assertEqual("ANALISTA-COMPARTIDA", row["license_id"])
            self.assertEqual(1, row["license_revision"])

    def test_expired_and_idle_sessions_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root, private_key = self._configure_security(directory)
            security.install_license(self._license(private_key, 1), "cliente", "clave-temporal-segura")

            token, _ = security.login("cliente", "clave-temporal-segura")
            expired = (datetime.now(UTC) - security.SESSION_ABSOLUTE_TTL - timedelta(seconds=1)).isoformat()
            with security.database() as connection:
                connection.execute(
                    "UPDATE sessions SET created_at=?,last_seen_at=? WHERE token_hash=?",
                    (expired, datetime.now(UTC).isoformat(), security._token_hash(token)),
                )
            self.assertIsNone(security.current_user(token))

            token, _ = security.login("cliente", "clave-temporal-segura")
            idle = (datetime.now(UTC) - security.SESSION_IDLE_TTL - timedelta(seconds=1)).isoformat()
            with security.database() as connection:
                connection.execute(
                    "UPDATE sessions SET last_seen_at=? WHERE token_hash=?",
                    (idle, security._token_hash(token)),
                )
            self.assertIsNone(security.current_user(token))
            self.assertTrue(root.is_dir())

    def test_password_change_revokes_other_sessions(self) -> None:
        with TemporaryDirectory() as directory:
            _, private_key = self._configure_security(directory)
            security.install_license(self._license(private_key, 1), "cliente", "clave-temporal-segura")
            first_token, _ = security.login("cliente", "clave-temporal-segura")
            second_token, _ = security.login("cliente", "clave-temporal-segura")

            replacement_token, user = security.change_password(first_token, "nueva-clave-segura")

            self.assertEqual("cliente", user["username"])
            self.assertIsNone(security.current_user(first_token))
            self.assertIsNone(security.current_user(second_token))
            self.assertIsNotNone(security.current_user(replacement_token))

    def test_repeated_login_failures_are_rate_limited(self) -> None:
        with TemporaryDirectory() as directory:
            _, private_key = self._configure_security(directory)
            security.install_license(self._license(private_key, 1), "cliente", "clave-temporal-segura")
            security._login_failures.clear()
            security._login_blocked_until.clear()

            for _ in range(security.LOGIN_MAX_FAILURES):
                self.assertIsNone(security.login("cliente", "incorrecta"))
            with self.assertRaises(security.LoginRateLimited):
                security.login("cliente", "clave-temporal-segura")

    def _configure_security(self, directory: str) -> tuple[Path, Ed25519PrivateKey]:
        root = Path(directory)
        private_key = Ed25519PrivateKey.generate()
        public_key_path = root / "license_public_key.pem"
        public_key_path.write_bytes(
            private_key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        for active_patch in (
            patch.object(security, "APP_DATA_DIR", root),
            patch.object(security, "DB_PATH", root / "users.db"),
            patch.object(security, "LICENSE_PATHS", (root / "license.json",)),
            patch.object(security, "PUBLIC_KEY_PATH", public_key_path),
        ):
            active_patch.start()
            self.addCleanup(active_patch.stop)
        self.addCleanup(security._login_failures.clear)
        self.addCleanup(security._login_blocked_until.clear)
        return root, private_key

    @staticmethod
    def _license(
        private_key: Ed25519PrivateKey,
        revision: int,
        license_id: str = "CLIENTE-001",
    ) -> bytes:
        payload = {
            "version": 2,
            "revision": revision,
            "licenseId": license_id,
            "customer": "Cliente",
            "issuedAt": datetime.now(UTC).date().isoformat(),
            "expiresAt": None,
            "modules": ["reports"],
            "provision": {
                "username": "cliente",
                "passwordHash": PasswordHasher().hash("clave-temporal-segura"),
                "role": "user",
            },
        }
        payload["signature"] = base64.b64encode(
            private_key.sign(security.canonical_license(payload))
        ).decode()
        return json.dumps(payload).encode()

import base64
import json
from datetime import UTC, datetime
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

    @staticmethod
    def _license(private_key: Ed25519PrivateKey, revision: int) -> bytes:
        payload = {
            "version": 2,
            "revision": revision,
            "licenseId": "CLIENTE-001",
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

from __future__ import annotations

import json
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from backend import security
from backend.cloud_backup import CloudHttpError, _SafeRedirectHandler, _client_id, _redirect_uri
from backend.cloud_sync import _merge_record, _merge_user, synchronize_onedrive
from backend.security import database
from backend.user_data import write_user_data


class CloudMergeTests(unittest.TestCase):
    def test_onedrive_uses_the_built_in_public_client(self) -> None:
        self.assertEqual(_client_id({}, "onedrive"), "41680243-1eed-44c7-8ac5-20ba966f8209")

    def test_onedrive_redirect_keeps_dynamic_port_on_localhost(self) -> None:
        redirect = _redirect_uri("http://127.0.0.1:54321/", "onedrive")
        self.assertEqual(redirect, "http://localhost:54321/api/cloud/auth/callback/onedrive")

    def test_cross_host_download_redirect_does_not_forward_authorization(self) -> None:
        request = urllib.request.Request(
            "https://graph.microsoft.com/v1.0/me/drive/special/approot:/file:/content",
            headers={"Authorization": "Bearer secret"},
        )

        redirected = _SafeRedirectHandler().redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://public.dm.files.1drv.com/download-token",
        )

        self.assertIsNotNone(redirected)
        self.assertIsNone(redirected.get_header("Authorization"))

    def test_distinct_records_are_preserved(self) -> None:
        local = {
            "collections": {
                "agenda": {
                    "kind": "list",
                    "records": {"a": {"updatedAt": "2026-01-01T00:00:00+00:00", "value": {"id": "a"}}},
                }
            }
        }
        remote = {
            "collections": {
                "agenda": {
                    "kind": "list",
                    "records": {"b": {"updatedAt": "2026-01-02T00:00:00+00:00", "value": {"id": "b"}}},
                }
            }
        }

        merged, conflicts = _merge_user(local, remote)

        self.assertEqual(set(merged["collections"]["agenda"]["records"]), {"a", "b"})
        self.assertEqual(conflicts, 0)

    def test_newer_deletion_wins(self) -> None:
        active = {"updatedAt": "2026-01-01T00:00:00+00:00", "value": {"id": "a"}}
        deleted = {"deletedAt": "2026-01-02T00:00:00+00:00", "deviceId": "work"}

        winner, conflict = _merge_record(active, deleted)

        self.assertEqual(winner, deleted)
        self.assertFalse(conflict)

    def test_same_value_from_another_device_is_not_a_conflict(self) -> None:
        local = {
            "updatedAt": "2026-01-01T00:00:00+00:00",
            "deviceId": "personal",
            "value": {"id": "a", "title": "Reunión"},
        }
        remote = {
            "updatedAt": "2026-01-01T00:00:00+00:00",
            "deviceId": "work",
            "value": {"id": "a", "title": "Reunión"},
        }

        _winner, conflict = _merge_record(local, remote)

        self.assertFalse(conflict)

    def test_etag_conflict_downloads_and_retries(self) -> None:
        empty = {"format": "agender.sync", "version": 1, "users": {}}
        user = {"id": 77, "username": "sync-user", "modules": []}
        upload_results = [
            CloudHttpError(412, "changed"),
            {"lastModifiedDateTime": "2026-01-01T00:00:00Z"},
        ]

        def upload(*_args: object) -> dict[str, str]:
            result = upload_results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with (
            patch("backend.cloud_sync._access_token", return_value="token"),
            patch("backend.cloud_sync._device_id", return_value="device"),
            patch(
                "backend.cloud_sync._download_document",
                side_effect=[(empty.copy(), "one", True), (empty.copy(), "two", True)],
            ) as download,
            patch("backend.cloud_sync._upload_document", side_effect=upload),
            patch("backend.cloud_sync._local_document", return_value={"collections": {}}),
            patch("backend.cloud_sync._apply_merged_user", return_value=0),
            patch("backend.cloud_sync.set_sync_result"),
        ):
            result = synchronize_onedrive(user)

        self.assertTrue(result["ok"])
        self.assertEqual(download.call_count, 2)


class TombstoneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.original_db = security.DB_PATH
        security.DB_PATH = Path(self.temporary.name) / "users.db"
        with database() as connection:
            connection.execute(
                """INSERT INTO users(id,username,password_hash,role,enabled,created_at)
                VALUES(1,'sync-user','hash','user',1,'2026-01-01T00:00:00+00:00')"""
            )
        self.user = {"id": 1, "username": "sync-user", "role": "user", "modules": ["agenda"]}

    def tearDown(self) -> None:
        security.DB_PATH = self.original_db
        self.temporary.cleanup()

    def test_deleting_a_record_creates_a_tombstone(self) -> None:
        write_user_data(self.user, "agender.agenda.events", [{"id": "event-1", "title": "QC"}])
        write_user_data(self.user, "agender.agenda.events", [])

        with database() as connection:
            row = connection.execute(
                "SELECT record_id,deleted_at FROM sync_tombstones WHERE user_id=1"
            ).fetchone()
            stored = connection.execute(
                "SELECT value_json FROM user_data WHERE user_id=1 AND data_key='agender.agenda.events'"
            ).fetchone()

        self.assertEqual(row["record_id"], "event-1")
        self.assertTrue(row["deleted_at"])
        self.assertEqual(json.loads(stored["value_json"]), [])


if __name__ == "__main__":
    unittest.main()

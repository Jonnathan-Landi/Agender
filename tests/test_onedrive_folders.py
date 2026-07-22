from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from backend.onedrive_folders import encode_share_url, materialize_source


class OneDriveFolderTests(TestCase):
    def test_share_url_is_encoded_for_graph(self) -> None:
        token = encode_share_url("https://example.sharepoint.com/:f:/g/folder?e=abc")
        self.assertTrue(token.startswith("u!"))
        self.assertNotIn("=", token)
        self.assertNotIn("/", token)

    def test_remote_files_are_cached_incrementally(self) -> None:
        user = {"id": 7, "username": "analista"}
        settings = {
            "rawDataSource": "onedrive",
            "rawOneDriveUrl": "https://example.sharepoint.com/:f:/g/folder?e=abc",
        }
        root_item = {"id": "root", "name": "Datos", "folder": {}, "parentReference": {"driveId": "drive"}}
        children = {
            "value": [
                {"id": "file", "name": "EST001.csv", "size": 4, "eTag": "one", "file": {}},
                {"id": "ignored", "name": "nota.pdf", "size": 2, "eTag": "two", "file": {}},
            ]
        }

        def graph(url: str, **_kwargs: object) -> dict:
            return root_item if "/shares/" in url else children

        with TemporaryDirectory() as temporary:
            with (
                patch("backend.onedrive_folders.REMOTE_CACHE_ROOT", Path(temporary)),
                patch("backend.onedrive_folders._access_token", return_value="token"),
                patch("backend.onedrive_folders._json_request", side_effect=graph),
                patch(
                    "backend.onedrive_folders.download_to_file",
                    side_effect=lambda _url, target, **_kwargs: target.write_bytes(b"data"),
                ) as download,
            ):
                root, first = materialize_source(user, settings, "raw")
                _root, second = materialize_source(user, settings, "raw")

                self.assertEqual(b"data", (Path(root) / "EST001.csv").read_bytes())
                self.assertEqual(1, first["remoteDownloaded"])
                self.assertEqual(0, second["remoteDownloaded"])
                self.assertEqual(1, second["remoteReused"])
                self.assertEqual(1, download.call_count)

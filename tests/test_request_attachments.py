from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from backend import request_attachments


class RequestAttachmentTests(TestCase):
    def setUp(self) -> None:
        self.user = {"id": 7, "username": "alandi", "modules": ["requests"]}
        self.record = {
            "id": "request-1234",
            "requester": "María Belén Arévalo",
            "attachments": [],
        }

    def test_save_is_local_and_creates_a_pending_upload(self) -> None:
        with (
            TemporaryDirectory() as directory,
            patch.object(request_attachments, "APP_DATA_DIR", Path(directory)),
            patch.object(request_attachments, "read_user_data", return_value={
                request_attachments.REQUESTS_KEY: [self.record]
            }),
        ):
            result = request_attachments.save_request_pdf_local(
                self.user, self.record["id"], "request", "Solicitud firmada.pdf", b"%PDF-1.7\ncontent"
            )
            folder = request_attachments._local_folder(self.user, result["folder"])
            self.assertTrue((folder / result["remoteName"]).is_file())
            self.assertTrue(request_attachments._pending_path(folder / result["remoteName"]).is_file())

        self.assertEqual("request", result["role"])
        self.assertEqual("Solicitud_firmada.pdf", result["name"])
        self.assertEqual("SOL_María Belén Arévalo", result["folder"])

    def test_pending_local_pdf_uploads_to_onedrive_in_background(self) -> None:
        with (
            TemporaryDirectory() as directory,
            patch.object(request_attachments, "APP_DATA_DIR", Path(directory)),
            patch.object(request_attachments, "read_user_data", return_value={
                request_attachments.REQUESTS_KEY: [self.record]
            }),
            patch.object(request_attachments, "_access_token", return_value="token"),
            patch.object(request_attachments, "_ensure_folder") as ensure_folder,
            patch.object(request_attachments, "_json_request", return_value={"id": "onedrive-item"}) as upload,
        ):
            attachment = request_attachments.save_request_pdf_local(
                self.user, self.record["id"], "request", "solicitud.pdf", b"%PDF-1.7\ncontent"
            )
            result = request_attachments.sync_request_pdf_to_onedrive(self.user, attachment)
            local_file = request_attachments._local_folder(self.user, attachment["folder"]) / attachment["remoteName"]
            self.assertFalse(request_attachments._pending_path(local_file).exists())

        self.assertEqual("onedrive-item", result["id"])
        self.assertEqual(3, ensure_folder.call_count)
        self.assertIn("/Solicitudes/", upload.call_args.args[0])

    def test_upload_rejects_non_pdf_content(self) -> None:
        with patch.object(request_attachments, "read_user_data", return_value={
            request_attachments.REQUESTS_KEY: [self.record]
        }):
            with self.assertRaisesRegex(ValueError, "PDF válido"):
                request_attachments.save_request_pdf_local(
                    self.user, self.record["id"], "request", "engaño.pdf", b"not a pdf"
                )

    def test_deleting_last_request_removes_its_complete_local_folder(self) -> None:
        with (
            TemporaryDirectory() as directory,
            patch.object(request_attachments, "APP_DATA_DIR", Path(directory)),
            patch.object(request_attachments, "read_user_data", return_value={
                request_attachments.REQUESTS_KEY: [self.record]
            }),
        ):
            attachment = request_attachments.save_request_pdf_local(
                self.user, self.record["id"], "request", "solicitud.pdf", b"%PDF-1.7\ncontent"
            )
            folder = request_attachments._local_folder(self.user, attachment["folder"])
            self.assertTrue(folder.is_dir())
            result = request_attachments.delete_request_documents_local(self.user, self.record["id"])
            self.assertFalse(folder.exists())
            self.assertFalse(result["shared"])

    def test_download_only_uses_attachment_registered_on_record(self) -> None:
        attachment = {
            "id": "a" * 32,
            "role": "response",
            "name": "respuesta.pdf",
            "remoteName": f"{'a' * 32}-respuesta.pdf",
            "folder": "Sol_Maria_request1",
        }
        record = {**self.record, "attachments": [attachment]}
        with (
            TemporaryDirectory() as directory,
            patch.object(request_attachments, "APP_DATA_DIR", Path(directory)),
            patch.object(request_attachments, "read_user_data", return_value={
                request_attachments.REQUESTS_KEY: [record]
            }),
            patch.object(request_attachments, "_access_token", return_value="token"),
            patch.object(request_attachments, "_bytes_request", return_value=b"%PDF-1.7\ncontent") as download,
        ):
            content, name = request_attachments.download_request_pdf(self.user, record["id"], attachment["id"])

        self.assertTrue(content.startswith(b"%PDF-"))
        self.assertEqual("respuesta.pdf", name)
        self.assertIn("Sol_Maria_request1", download.call_args.args[0])


if __name__ == "__main__":
    import unittest

    unittest.main()

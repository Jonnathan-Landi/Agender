import unittest
from pathlib import Path


class RequestsBoardIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent
        cls.document = (root / "frontend" / "index.html").read_text(encoding="utf-8")
        cls.controller = (root / "frontend" / "js" / "features" / "requests.js").read_text(encoding="utf-8")
        cls.styles = (root / "frontend" / "css" / "requests.css").read_text(encoding="utf-8")
        cls.backend = (root / "backend" / "main.py").read_text(encoding="utf-8")

    def test_requests_has_list_and_board_views(self):
        self.assertIn('data-request-view="list"', self.document)
        self.assertIn('data-request-view="board"', self.document)
        self.assertIn('id="request-status-board"', self.document)

    def test_board_reuses_request_records(self):
        self.assertEqual(self.controller.count('const STORAGE_KEY = "agender.request.records"'), 1)
        self.assertIn("renderStatusBoard();", self.controller)
        self.assertNotIn("agender.request.board", self.controller)

    def test_columns_create_and_move_requests(self):
        self.assertIn('data-request-board-action="add"', self.controller)
        self.assertIn('data-request-board-status="${escapeHtml(status)}"', self.controller)
        self.assertIn('statusBoard.addEventListener("pointerdown", handleBoardPointerDown)', self.controller)
        self.assertIn('statusBoard.addEventListener("pointerup", handleBoardPointerUp)', self.controller)

    def test_context_menu_and_safe_delete_dialog(self):
        self.assertIn('id="request-context-menu"', self.document)
        self.assertIn('id="request-delete-dialog"', self.document)
        self.assertIn('body.addEventListener("contextmenu", handleRequestContextMenu)', self.controller)
        self.assertIn('statusBoard.addEventListener("contextmenu", handleRequestContextMenu)', self.controller)
        self.assertIn("requestRecordDeletion", self.controller)
        self.assertNotIn("confirm(", self.controller)

    def test_table_actions_are_available_only_from_the_context_menu(self):
        self.assertNotIn("<th>Acciones</th>", self.document)
        self.assertNotIn('class="row-actions"', self.controller)
        self.assertIn('data-request-id="${record.id}" tabindex="0"', self.controller)
        self.assertIn('data-request-menu-action="edit"', self.document)

    def test_delete_removes_documents_before_removing_the_request(self):
        self.assertIn('/documents`, { method: "DELETE" }', self.controller)
        self.assertIn('@app.delete("/api/requests/{record_id}/documents")', self.backend)
        self.assertIn('data-request-menu-action="delete"', self.document)
        self.assertIn('data-request-menu-action="open-folder"', self.document)
        self.assertIn("&#xED25;", self.document)
        self.assertIn("openRequestFolder", self.controller)
        self.assertIn("/folder/open", self.controller)

    def test_priority_and_workflow_categories(self):
        for value in ("Alta", "Media", "Baja"):
            self.assertIn(value, self.document)
        for value in ("Recibido", "En formalización", "Despachado por Quipux", "Entregado", "Archivado"):
            self.assertIn(value, self.document)
        self.assertIn('const PRIORITIES = ["Alta", "Media", "Baja"]', self.controller)
        self.assertIn("normalizeStatus", self.controller)

    def test_table_keeps_status_quick_choice(self):
        row_template = self.controller.split("function rowTemplate", 1)[1].split("function choiceControlTemplate", 1)[0]
        board_template = self.controller.split("function boardCardTemplate", 1)[1].split(
            "function handleBoardClick", 1
        )[0]
        self.assertIn("choiceControlTemplate(record, \"status\", STATUSES)", row_template)
        self.assertNotIn("choiceControlTemplate(record, \"status\", STATUSES)", board_template)
        self.assertIn("handleQuickChoice", self.controller)
        self.assertIn('record.status = option.dataset.requestChoiceValue', self.controller)

    def test_new_request_fields_and_conditional_response_document(self):
        for field_id in (
            "requester", "request-document", "request-date", "request-objective",
            "requested-information", "status", "request-priority", "response-date", "response-document",
            "request-observations",
        ):
            self.assertIn(f'id="{field_id}"', self.document)
        self.assertNotIn('id="request-number"', self.document)
        self.assertIn("syncResponseDocumentRequirement", self.controller)
        self.assertIn("fields.responseDocument.required = Boolean(fields.responseDate.value)", self.controller)

    def test_numbers_follow_request_date_order(self):
        self.assertIn("function sortedRecords", self.controller)
        self.assertIn('(left.requestDate || "9999-12-31").localeCompare', self.controller)
        self.assertIn("function requestNumber", self.controller)

    def test_table_uses_wrapped_headers_and_fixed_layout(self):
        self.assertIn("Información<br>solicitada", self.document)
        self.assertIn("table-layout: fixed", self.styles)
        self.assertIn("min-width: 0", self.styles)

    def test_obsolete_request_schema_is_removed(self):
        obsolete_fields = (
            "EVALUATIONS",
            "normalizeEvaluation",
            "record.reference",
            "record.requestedData",
            "record.deliveryDate",
        )
        for obsolete in obsolete_fields:
            self.assertNotIn(obsolete, self.controller)

    def test_export_uses_excel_save_dialog_endpoint_and_all_records(self):
        self.assertIn('id="export-excel"', self.document)
        self.assertIn('fetch("/api/requests/export-excel"', self.controller)
        self.assertIn("const rows = sortedRecords().map", self.controller)
        self.assertNotIn("exportCsv", self.controller)
        self.assertNotIn("text/csv", self.controller)

    def test_pdf_attachments_use_onedrive_endpoints_and_internal_viewer(self):
        for field_id in ("request-pdf", "response-pdf", "additional-pdfs", "request-pdf-dialog", "request-pdf-frame"):
            self.assertIn(f'id="{field_id}"', self.document)
        self.assertIn("uploadPendingFiles", self.controller)
        self.assertIn("/attachments", self.controller)
        self.assertIn("openPdfViewer", self.controller)
        self.assertIn("data-request-pdf-view", self.controller)

    def test_pdf_pickers_are_compact_and_dates_use_iso_format(self):
        self.assertEqual(2, self.document.count('class="button secondary request-pdf-picker"'))
        self.assertGreaterEqual(self.document.count("&#xEA90;"), 2)
        self.assertIn("function formatIsoDate", self.controller)
        self.assertIn("formatIsoDate(record.requestDate)", self.controller)
        self.assertIn("formatIsoDate(record.responseDate)", self.controller)
        self.assertEqual(2, self.document.count('placeholder="AAAA-MM-DD"'))
        self.assertIn('id="request-date-picker" type="date"', self.document)
        self.assertIn('id="response-date-picker" type="date"', self.document)
        self.assertIn("selectCalendarDate", self.controller)
        self.assertIn("function isValidIsoDate", self.controller)


if __name__ == "__main__":
    unittest.main()

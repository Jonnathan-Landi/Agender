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

    def test_requests_owns_its_visual_components_without_diary_css(self):
        requests_markup = self.document.split('<section class="view" id="requests-view"', 1)[1].split(
            '<section class="view" id="diary-view"', 1
        )[0]
        self.assertNotIn("diary-", requests_markup)
        self.assertNotIn("diary-", self.controller)
        for class_name in ("request-view-tab", "request-board-column", "request-context-menu"):
            self.assertIn(f".{class_name}", self.styles)

    def test_form_and_filters_use_winui_comboboxes(self):
        self.assertIn('data-request-form-combobox="priority"', self.document)
        self.assertIn('data-request-form-combobox="status"', self.document)
        self.assertEqual(2, self.document.count("data-request-filter-combobox>"))
        self.assertNotIn('<select id="request-priority"', self.document)
        self.assertNotIn('<select id="status"', self.document)
        self.assertNotIn('<select id="request-filter"', self.document)
        self.assertNotIn('<select id="status-filter"', self.document)
        self.assertIn("handleFormComboboxClick", self.controller)
        self.assertIn("handleFilterComboboxClick", self.controller)

    def test_board_reuses_request_records(self):
        self.assertEqual(self.controller.count('const STORAGE_KEY = "agender.request.records"'), 1)
        self.assertIn("renderStatusBoard();", self.controller)
        self.assertNotIn("agender.request.board", self.controller)

    def test_delivered_cards_expire_only_from_the_board_after_two_days(self):
        board_renderer = self.controller.split("function renderStatusBoard", 1)[1].split(
            "function boardColumnTemplate", 1
        )[0]
        list_renderer = self.controller.split("function render()", 1)[1].split(
            "function selectRequestView", 1
        )[0]
        self.assertIn("isExpiredBoardRecord(record)", board_renderer)
        self.assertNotIn("isExpiredBoardRecord(record)", list_renderer)
        self.assertIn('record.status !== "Entregado"', self.controller)
        self.assertIn("2 * 24 * 60 * 60 * 1000", self.controller)
        self.assertIn("record.statusChangedAt = new Date().toISOString()", self.controller)

    def test_columns_create_and_move_requests(self):
        self.assertIn('data-request-board-action="add"', self.controller)
        self.assertIn('data-request-board-status="${escapeHtml(status)}"', self.controller)
        self.assertIn('statusBoard.addEventListener("pointerdown", handleBoardPointerDown)', self.controller)
        self.assertIn('statusBoard.addEventListener("pointerup", handleBoardPointerUp)', self.controller)

    def test_busy_board_columns_scroll_without_covering_the_add_button(self):
        board = self.styles.split("#requests-view .request-board {", 1)[1].split("}", 1)[0]
        cards = self.styles.split("#requests-view .request-board-cards {", 1)[1].split("}", 1)[0]
        add = self.styles.split("#requests-view .request-board-add {", 1)[1].split("}", 1)[0]
        self.assertIn("height: 100%", board)
        self.assertIn("overflow-y: hidden", board)
        self.assertIn("overflow-y: auto", cards)
        self.assertIn("flex: 1", cards)
        self.assertIn("flex: 0 0 auto", add)

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

    def test_summary_counts_every_request_status_with_matching_visuals(self):
        for metric in ("received", "formalizing", "dispatched", "delivered", "archived"):
            self.assertIn(f'id="metric-{metric}"', self.document)
        self.assertIn('item.status === "Despachado por Quipux"', self.controller)
        self.assertIn('item.status === "Archivado"', self.controller)

    def test_status_summary_is_a_separate_interactive_filter_row(self):
        self.assertIn('data-request-status-tab="Recibido"', self.document)
        self.assertIn('data-request-status-tab="Entregado"', self.document)
        self.assertIn("handleStatusTabClick", self.controller)
        self.assertIn("renderStatusTabs", self.controller)
        self.assertIn('document.querySelector(".requests-summary").hidden = activeView !== "list"', self.controller)
        self.assertIn(".requests-summary[hidden]", self.styles)
        self.assertNotIn("linear-gradient(135deg", self.styles)

    def test_request_list_is_paginated_without_limiting_excel_export(self):
        self.assertIn('id="request-pagination-pages"', self.document)
        self.assertIn('id="request-page-size"', self.document)
        self.assertIn("filtered.slice(start, start + pageSize)", self.controller)
        export = self.controller.split("async function exportExcel", 1)[1]
        self.assertIn("sortedRecords().map", export)
        self.assertNotIn("pageRecords", export)

    def test_sparse_request_tables_keep_theme_background_and_soft_pagination(self):
        self.assertIn("#requests-view #request-list-view .table-wrap", self.styles)
        self.assertIn("background: var(--panel)", self.styles)
        pagination = self.styles.split(".request-pagination button.active", 1)[1].split("}", 1)[0]
        self.assertIn("background: var(--accent-soft)", pagination)
        self.assertNotIn("background: var(--accent);", pagination)

    def test_request_heading_has_no_redundant_description(self):
        heading = self.document.split('class="requests-heading"', 1)[1].split("</div>", 1)[0]
        self.assertNotIn("Gestiona y realiza seguimiento", heading)

    def test_table_keeps_status_quick_choice(self):
        row_template = self.controller.split("function rowTemplate", 1)[1].split("function choiceControlTemplate", 1)[0]
        board_template = self.controller.split("function boardCardTemplate", 1)[1].split(
            "function handleBoardClick", 1
        )[0]
        self.assertIn("choiceControlTemplate(record)", row_template)
        self.assertNotIn("choiceControlTemplate(record)", board_template)
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

    def test_user_type_is_stored_and_exported_but_hidden_from_table(self):
        self.assertIn('id="request-user-type"', self.document)
        self.assertIn('data-request-form-value="Externo"', self.document)
        self.assertIn('data-request-form-value="Interno"', self.document)
        self.assertIn("userType: fields.userType.value", self.controller)
        self.assertIn('userType: USER_TYPES.includes(record.userType) ? record.userType : "Externo"', self.controller)
        row_template = self.controller.split("function rowTemplate", 1)[1].split(
            "function documentCellTemplate", 1
        )[0]
        export = self.controller.split("async function exportExcel", 1)[1]
        self.assertNotIn("escapeHtml(record.userType)", row_template)
        table_header = self.document.split('<tbody id="requests-body">', 1)[0].rsplit("<thead>", 1)[1]
        self.assertNotIn("<th>Usuario</th>", table_header)
        self.assertIn('"Usuario"', export)
        self.assertIn("record.userType", export)

    def test_request_table_uses_more_available_vertical_space(self):
        self.assertIn("#requests-view.active", self.styles)
        self.assertIn("height: calc(100vh - 56px)", self.styles)
        self.assertIn("#requests-view #request-list-view .table-panel", self.styles)
        self.assertIn("max-height: none", self.styles)

    def test_numbers_follow_request_date_order(self):
        self.assertIn("function sortedRecords", self.controller)
        self.assertIn('(left.requestDate || "9999-12-31").localeCompare', self.controller)
        self.assertIn("function requestNumber", self.controller)

    def test_table_uses_wrapped_headers_and_fixed_layout(self):
        self.assertIn("Información<br>solicitada", self.document)
        self.assertIn("table-layout: fixed", self.styles)
        self.assertIn("min-width: 0", self.styles)

    def test_objective_and_requested_information_receive_more_table_width(self):
        self.assertIn("th:nth-child(5) { width: 15.5%; }", self.styles)
        self.assertIn("th:nth-child(6) { width: 15.5%; }", self.styles)
        self.assertIn("th:nth-child(7) { width: 7%; }", self.styles)
        self.assertIn("th:nth-child(8) { width: 5%; }", self.styles)

    def test_status_selector_is_fixed_and_truncates_long_labels(self):
        self.assertIn("width: 104px", self.styles)
        self.assertIn("text-overflow: ellipsis", self.styles)
        self.assertIn('title="${escapeHtml(current)}"', self.controller)

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
        self.assertIn('data-request-calendar="request"', self.document)
        self.assertIn('data-request-calendar="response"', self.document)
        self.assertIn("renderCalendar", self.controller)
        self.assertIn("isoFromDate", self.controller)
        self.assertIn("function isValidIsoDate", self.controller)

    def test_form_disables_autofill_and_enables_spanish_spellcheck(self):
        self.assertIn('id="request-form" autocomplete="off" lang="es"', self.document)
        for field_id in ("requester", "request-objective", "requested-information", "request-observations"):
            field = self.document.split(f'id="{field_id}"', 1)[1].split(">", 1)[0]
            self.assertIn('spellcheck="true"', field)
        self.assertGreaterEqual(self.document.count('autocomplete="off"'), 7)


if __name__ == "__main__":
    unittest.main()

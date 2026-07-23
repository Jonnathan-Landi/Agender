import unittest
from pathlib import Path


class DiaryBoardIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).resolve().parent.parent
        cls.document = (cls.project_root / "frontend" / "index.html").read_text(encoding="utf-8")
        cls.controller = (
            cls.project_root / "frontend" / "js" / "features" / "diary.js"
        ).read_text(encoding="utf-8")
        cls.styles = (
            cls.project_root / "frontend" / "css" / "diary.css"
        ).read_text(encoding="utf-8")

    def test_diary_has_plan_and_status_board_views(self):
        self.assertIn('data-diary-view="plan"', self.document)
        self.assertIn('data-diary-view="board"', self.document)
        self.assertIn('id="diary-status-board"', self.document)

    def test_diary_toolbar_has_no_obsolete_today_button(self):
        self.assertNotIn('id="diary-today"', self.document)
        self.assertNotIn("function goToday()", self.controller)
        self.assertIn("function today()", self.controller)

    def test_plan_uses_structured_task_columns_and_daily_summary(self):
        self.assertIn('class="diary-list-columns"', self.document)
        for label in ("Tarea", "Categoría", "Vencimiento", "Estado", "Progreso"):
            self.assertIn(label, self.document)
        summary_ids = (
            "diary-status-chart",
            "diary-chart-legend",
            "diary-upcoming-list",
            "diary-overdue-list",
            "diary-overdue-count",
        )
        for element_id in summary_ids:
            self.assertIn(f'id="{element_id}"', self.document)
        self.assertIn("function updateDaySummary", self.controller)
        self.assertIn("task.date === date", self.controller)

    def test_side_panel_matches_the_three_card_design(self):
        self.assertNotIn("Foco del día", self.document)
        self.assertNotIn("Resumen del día", self.document)
        for title in ("Tareas por estado", "Próximos vencimientos", "Pendientes vencidas"):
            self.assertIn(title, self.document)
        self.assertNotIn("FOCUS_KEY", self.controller)
        self.assertIn("function renderOverdueTasks", self.controller)

    def test_current_layout_has_no_legacy_override_block(self):
        self.assertNotIn("Current Diario workspace", self.styles)
        base_styles = self.styles.split("@media", 1)[0]
        for selector in (".diary-layout {", ".diary-task-panel {", ".diary-task-list {"):
            self.assertEqual(base_styles.count(selector), 1)
        self.assertIn("grid-template-rows: auto repeat(2, minmax(150px, 1fr))", self.styles)

    def test_work_list_date_is_selected_from_its_header(self):
        filter_panel = self.document.split('id="diary-filter-panel"', 1)[1].split("</div>", 1)[0]
        list_head = self.document.split('class="diary-list-head"', 1)[1].split("</div>", 2)[0]
        self.assertNotIn('id="diary-date"', filter_panel)
        self.assertIn('id="diary-date"', list_head)
        self.assertIn('class="diary-date-selector"', list_head)
        self.assertIn('id="diary-date-trigger"', list_head)
        self.assertIn("&#xE787;", list_head)
        self.assertIn('selectedDate.addEventListener("change", handleDateChange)', self.controller)
        self.assertIn(
            'document.querySelector("#diary-date-trigger").addEventListener("click", openDatePicker)',
            self.controller,
        )
        self.assertIn("selectedDate.showPicker()", self.controller)

    def test_calendar_icon_and_column_headers_are_prominent_and_aligned(self):
        self.assertIn("font-size: 22px", self.styles)
        self.assertIn("place-items: center", self.styles)
        list_columns = self.styles.split(".diary-list-columns {", 1)[1].split("}", 1)[0]
        self.assertIn("font-size: 0.76rem", list_columns)
        self.assertIn("font-weight: 750", list_columns)
        self.assertIn("text-align: center", list_columns)

    def test_task_rows_render_category_due_date_status_progress_and_actions(self):
        template = self.controller.split("function taskTemplate", 1)[1].split(
            "function handleDateChange", 1
        )[0]
        task_classes = (
            "diary-task-category",
            "diary-task-due",
            "diary-task-status",
            "diary-task-progress",
            "diary-task-actions",
        )
        for class_name in task_classes:
            self.assertIn(class_name, template)

    def test_upcoming_deadlines_open_the_existing_task_editor(self):
        self.assertIn("function renderUpcomingTasks", self.controller)
        self.assertIn('task.status !== "Finalizada"', self.controller)
        self.assertIn("function renderDeadlineList", self.controller)
        self.assertIn('data-deadline-task="${escapeHtml(task.id)}"', self.controller)
        self.assertIn("openTaskById(button.dataset.deadlineTask)", self.controller)

    def test_upcoming_and_overdue_cards_list_every_matching_task(self):
        self.assertNotIn(".slice(0, 3)", self.controller)
        self.assertIn('renderDeadlineList("#diary-upcoming-list"', self.controller)
        self.assertIn('renderDeadlineList("#diary-overdue-list"', self.controller)
        self.assertIn("${escapeHtml(task.title)}", self.controller)

    def test_status_chart_is_large_and_stacked_above_its_legend(self):
        chart_card = self.styles.split(".diary-chart-card {", 1)[1].split("}", 1)[0]
        self.assertIn("display: flex", chart_card)
        self.assertIn("flex-direction: column", chart_card)
        self.assertIn("width: min(200px, 82%)", self.styles)
        self.assertIn("aspect-ratio: 1", self.styles)
        self.assertIn("margin: 0 auto 18px", self.styles)
        self.assertIn("font-size: 0.78rem", self.styles)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", self.styles)

    def test_board_reuses_the_existing_task_collection(self):
        self.assertEqual(self.controller.count('const TASKS_KEY = "agender.diary.tasks"'), 1)
        self.assertIn("renderStatusBoard();", self.controller)
        self.assertIn("saveTasks();", self.controller)
        self.assertNotIn("agender.diary.board", self.controller)

    def test_each_status_column_can_add_and_move_tasks(self):
        self.assertIn('data-board-action="add"', self.controller)
        self.assertIn('data-board-status="${escapeHtml(status)}"', self.controller)
        self.assertIn('statusBoard.addEventListener("pointerdown", handleBoardPointerDown)', self.controller)
        self.assertIn('statusBoard.addEventListener("pointerup", handleBoardPointerUp)', self.controller)

    def test_column_header_has_no_duplicate_add_button(self):
        header = self.controller.split('<header>', 1)[1].split("</header>", 1)[0]
        self.assertNotIn('data-board-action="add"', header)

    def test_board_supports_quick_priority_changes(self):
        self.assertIn("data-board-priority-toggle", self.controller)
        self.assertIn("data-board-priority-value", self.controller)
        self.assertIn("updateBoardPriority", self.controller)
        self.assertIn("task.priority = value", self.controller)

    def test_priority_change_preserves_the_card_position(self):
        board_renderer = self.controller.split("function renderStatusBoard", 1)[1].split(
            "function boardColumnTemplate", 1
        )[0]
        self.assertNotIn(".sort(compareTasks)", board_renderer)

    def test_priority_uses_the_winui_chevron_without_overriding_its_font(self):
        self.assertIn("&#xE70D;", self.controller)
        self.assertIn(".diary-board-priority > span:first-child", self.styles)
        self.assertIn('.diary-board-priority > .font-icon', self.styles)
        self.assertIn('font-family: "Segoe Fluent Icons"', self.styles)
        self.assertNotIn(".diary-board-priority > span {", self.styles)

    def test_board_has_no_native_priority_selector_residue(self):
        self.assertNotIn('<select class="diary-priority', self.controller)
        self.assertNotIn("handleBoardQuickChange", self.controller)
        self.assertNotIn('querySelectorAll("select")', self.controller)

    def test_card_click_does_not_open_editor(self):
        click_handler = self.controller.split("function handleBoardClick", 1)[1].split(
            "function updateBoardPriority", 1
        )[0]
        self.assertNotIn("openTaskById", click_handler)

    def test_context_menu_edits_and_deletes_tasks(self):
        self.assertIn('id="diary-board-context-menu"', self.document)
        self.assertIn('id="diary-delete-dialog"', self.document)
        self.assertIn('data-board-menu-action="edit"', self.document)
        self.assertIn('data-board-menu-action="delete"', self.document)
        self.assertIn("handleBoardContextMenu", self.controller)
        self.assertIn("handleBoardMenuAction", self.controller)
        self.assertIn("requestTaskDeletion", self.controller)
        self.assertIn("confirmTaskDeletion", self.controller)
        self.assertNotIn("confirm(", self.controller)

    def test_drag_uses_a_floating_ghost_and_drop_placeholder(self):
        self.assertIn("createBoardDragGhost", self.controller)
        self.assertIn("diary-board-drop-placeholder", self.controller)

    def test_finalized_cards_expire_only_from_the_board_after_two_days(self):
        board_renderer = self.controller.split("function renderStatusBoard", 1)[1].split(
            "function boardColumnTemplate", 1
        )[0]
        plan_renderer = self.controller.split("function getVisibleTasks", 1)[1].split(
            "function taskTemplate", 1
        )[0]
        self.assertIn("isExpiredBoardTask(task)", board_renderer)
        self.assertNotIn("isExpiredBoardTask(task)", plan_renderer)
        self.assertIn('task.status !== "Finalizada"', self.controller)
        self.assertIn("2 * 24 * 60 * 60 * 1000", self.controller)
        self.assertIn("task.statusChangedAt = task.updatedAt", self.controller)


if __name__ == "__main__":
    unittest.main()

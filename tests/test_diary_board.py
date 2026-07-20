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


if __name__ == "__main__":
    unittest.main()

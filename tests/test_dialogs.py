"""Тесты сервиса диалогов: создание, удаление, переименование, режимы."""

import json
import tempfile
import unittest
from pathlib import Path

from keyboards.menus import dialogs_menu
from models.entities import Message
from services.dialog_service import DialogService
from storage.user_store import UserStore


class DialogServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = UserStore(Path(self._tmp.name) / "users")
        self.user = self.store.ensure_user(1)
        self.service = DialogService(self.store)

    def test_create_new_dialog_becomes_active(self) -> None:
        dialog = self.service.create(self.user)

        self.assertEqual(len(dialog.id), 8)
        self.assertEqual(dialog.title, "Диалог 2")
        self.assertEqual(dialog.mode_id, "assistant")
        self.assertEqual(dialog.messages, [])
        self.assertEqual(self.user.active_dialog_id, dialog.id)
        self.assertIs(self.service.get_active(self.user), dialog)
        self.assertIs(self.user.dialogs[-1], dialog)

    def test_cannot_delete_last_dialog(self) -> None:
        deleted = self.service.delete(self.user, "main")

        self.assertIs(deleted, False)
        self.assertEqual(len(self.user.dialogs), 1)
        self.assertEqual(self.user.dialogs[0].id, "main")
        self.assertEqual(self.user.active_dialog_id, "main")

    def test_delete_active_switches_to_remaining(self) -> None:
        second = self.service.create(self.user)
        self.assertEqual(self.user.active_dialog_id, second.id)

        deleted = self.service.delete(self.user, second.id)

        self.assertIs(deleted, True)
        self.assertEqual(len(self.user.dialogs), 1)
        self.assertEqual(self.user.active_dialog_id, "main")

    def test_rename_empty_keeps_old_title(self) -> None:
        dialog = self.service.rename(self.user, "main", "   ")

        self.assertEqual(dialog.title, "Основной")

    def test_set_mode_changes_only_target_dialog(self) -> None:
        second = self.service.create(self.user)

        dialog = self.service.set_mode(self.user, "main", "teacher")

        self.assertEqual(dialog.mode_id, "teacher")
        self.assertEqual(second.mode_id, "assistant")

    def test_create_limit_is_eight(self) -> None:
        for _ in range(7):
            self.service.create(self.user)
        self.assertEqual(len(self.user.dialogs), 8)

        with self.assertRaises(ValueError) as context:
            self.service.create(self.user)

        self.assertEqual(str(context.exception), "Достигнут лимит диалогов")
        self.assertEqual(len(self.user.dialogs), 8)

    def test_dialogs_menu_with_eight_dialogs_fits_six_rows(self) -> None:
        for _ in range(7):
            self.service.create(self.user)

        keyboard = dialogs_menu(self.user.dialogs, self.user.active_dialog_id)
        rows = json.loads(keyboard.get_json())["buttons"]

        self.assertEqual(len(self.user.dialogs), 8)
        self.assertLessEqual(len(rows), 6)

    def test_clear_history(self) -> None:
        self.user.dialogs[0].messages.append(Message(role="user", content="Привет"))

        self.service.clear_history(self.user, "main")

        self.assertEqual(self.user.dialogs[0].messages, [])


if __name__ == "__main__":
    unittest.main()

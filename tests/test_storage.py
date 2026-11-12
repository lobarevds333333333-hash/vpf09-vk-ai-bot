"""Тесты JSON-хранилища профилей пользователей."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from storage.user_store import UserStore
from models.entities import Message


class UserStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.users_dir = Path(self._tmp.name) / "users"
        self.store = UserStore(self.users_dir)

    def test_ensure_user_creates_default_dialog(self) -> None:
        user = self.store.ensure_user(42)

        self.assertEqual(user.user_id, 42)
        self.assertEqual(user.active_dialog_id, "main")
        self.assertEqual(len(user.dialogs), 1)
        dialog = user.dialogs[0]
        self.assertEqual(dialog.id, "main")
        self.assertEqual(dialog.title, "Основной")
        self.assertEqual(dialog.mode_id, "assistant")
        self.assertEqual(dialog.messages, [])
        self.assertEqual(user.facts, [])

    def test_save_load_roundtrip(self) -> None:
        user = self.store.ensure_user(7)
        timestamp = datetime.now().isoformat(timespec="seconds")
        user.dialogs[0].messages.append(
            Message(role="user", content="Привет", timestamp=timestamp)
        )
        self.store.save(user)

        loaded = UserStore(self.users_dir).load(7)

        self.assertEqual(loaded.to_dict(), user.to_dict())
        message = loaded.dialogs[0].messages[0]
        self.assertEqual(message.role, "user")
        self.assertEqual(message.content, "Привет")
        self.assertEqual(message.timestamp, timestamp)

    def test_corrupted_json_recovered(self) -> None:
        self.users_dir.mkdir(parents=True)
        path = self.users_dir / "5.json"
        path.write_text("not json", encoding="utf-8")

        user = self.store.load(5)

        self.assertEqual(user.user_id, 5)
        self.assertEqual(user.active_dialog_id, "main")
        self.assertEqual(len(user.dialogs), 1)
        self.assertEqual(user.dialogs[0].mode_id, "assistant")
        self.assertTrue((self.users_dir / "5.json.bak").exists())


if __name__ == "__main__":
    unittest.main()

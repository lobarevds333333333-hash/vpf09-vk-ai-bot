"""Тесты JSON-хранилища профилей пользователей."""

import json
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

        with self.assertLogs("storage.user_store", level="WARNING"):
            user = self.store.load(5)

        self.assertEqual(user.user_id, 5)
        self.assertEqual(user.active_dialog_id, "main")
        self.assertEqual(len(user.dialogs), 1)
        self.assertEqual(user.dialogs[0].mode_id, "assistant")
        self.assertTrue((self.users_dir / "5.json.bak").exists())

    def test_binary_garbage_moved_to_bak_with_warning(self) -> None:
        self.users_dir.mkdir(parents=True)
        path = self.users_dir / "9.json"
        path.write_bytes(b"\xff\xfe\x00\x80garbage")

        with self.assertLogs("storage.user_store", level="WARNING") as logs:
            user = self.store.load(9)

        self.assertIn("9", "\n".join(logs.output))
        self.assertEqual(user.user_id, 9)
        self.assertEqual(user.active_dialog_id, "main")
        self.assertEqual(len(user.dialogs), 1)
        self.assertEqual(user.dialogs[0].id, "main")
        self.assertTrue((self.users_dir / "9.json.bak").exists())
        self.assertFalse(path.exists())

    def test_empty_object_payload_returns_default_profile(self) -> None:
        self.users_dir.mkdir(parents=True)
        path = self.users_dir / "11.json"
        path.write_text("{}", encoding="utf-8")

        with self.assertLogs("storage.user_store", level="WARNING"):
            user = self.store.load(11)

        self.assertEqual(user.user_id, 11)
        self.assertEqual(user.active_dialog_id, "main")
        self.assertEqual(len(user.dialogs), 1)
        self.assertEqual(user.dialogs[0].id, "main")
        self.assertTrue((self.users_dir / "11.json.bak").exists())

    def test_empty_dialogs_repaired_with_default(self) -> None:
        self.users_dir.mkdir(parents=True)
        path = self.users_dir / "12.json"
        path.write_text(
            json.dumps(
                {
                    "user_id": 12,
                    "active_dialog_id": "gone",
                    "facts": [],
                    "dialogs": [],
                }
            ),
            encoding="utf-8",
        )

        with self.assertLogs("storage.user_store", level="WARNING"):
            user = self.store.load(12)

        self.assertEqual(len(user.dialogs), 1)
        self.assertEqual(user.dialogs[0].id, "main")
        self.assertEqual(user.dialogs[0].title, "Основной")
        self.assertEqual(user.active_dialog_id, "main")

    def test_dangling_active_dialog_repaired_to_first(self) -> None:
        self.users_dir.mkdir(parents=True)
        path = self.users_dir / "13.json"
        path.write_text(
            json.dumps(
                {
                    "user_id": 13,
                    "active_dialog_id": "missing",
                    "facts": [],
                    "dialogs": [
                        {
                            "id": "first",
                            "title": "Первый",
                            "mode_id": "teacher",
                            "messages": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        with self.assertLogs("storage.user_store", level="WARNING"):
            user = self.store.load(13)

        self.assertEqual(user.active_dialog_id, "first")
        self.assertEqual(len(user.dialogs), 1)


if __name__ == "__main__":
    unittest.main()

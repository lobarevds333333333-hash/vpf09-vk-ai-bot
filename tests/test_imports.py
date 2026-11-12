"""Smoke-тест: модули бота импортируются без запуска бота и без сети."""

import json
import unittest

from vkbottle import Keyboard

import main
from bot.handlers import RenameState, build_labeler
from keyboards.menus import main_menu, modes_menu
from utils.typing import typing


class ImportsTest(unittest.TestCase):
    def test_modules_import_and_main_menu_is_non_empty_keyboard(self) -> None:
        keyboard = main_menu()

        self.assertIsInstance(keyboard, Keyboard)
        self.assertTrue(keyboard.get_json())

        data = json.loads(keyboard.get_json())
        labels = [
            button["action"]["label"]
            for row in data["buttons"]
            for button in row
        ]
        self.assertTrue(data["inline"])
        self.assertIn("🆕 Новый диалог", labels)
        self.assertIn("❓ Помощь", labels)

        modes_data = json.loads(modes_menu("assistant").get_json())
        mode_labels = [
            button["action"]["label"]
            for row in modes_data["buttons"]
            for button in row
        ]
        self.assertIn("Ментор по Python", mode_labels)
        self.assertLessEqual(len(modes_data["buttons"]), 6)

        self.assertEqual(RenameState.WAIT_NAME, "rename_wait_name")
        self.assertTrue(callable(build_labeler))
        self.assertTrue(callable(typing))
        self.assertTrue(callable(main.main))


if __name__ == "__main__":
    unittest.main()

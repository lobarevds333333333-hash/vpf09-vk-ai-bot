"""Тесты конфигурации: режимы общения и числовые лимиты."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from config.settings import MODES, Settings, load_settings


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "vk_token": "token",
        "openrouter_api_key": "key",
        "openrouter_model": "model",
        "openrouter_base_url": "https://example.invalid/v1",
        "max_message_len": 4000,
        "max_history": 100,
        "max_dialogs": 8,
        "users_dir": Path("users"),
    }
    values.update(overrides)
    return Settings(**values)


class ModesTest(unittest.TestCase):
    def test_six_modes_with_unique_titles(self) -> None:
        self.assertEqual(len(MODES), 6)
        titles = [mode.title for mode in MODES.values()]
        self.assertEqual(len(set(titles)), 6)
        for mode in MODES.values():
            self.assertTrue(mode.prompt, mode.id)

    def test_python_mentor_mode_exists(self) -> None:
        self.assertEqual(MODES["python_mentor"].title, "Ментор по Python")


class SettingsValidationTest(unittest.TestCase):
    def test_supported_limits_are_accepted(self) -> None:
        settings = make_settings(
            max_message_len=4000,
            max_history=1,
            max_dialogs=8,
        )

        self.assertEqual(settings.max_message_len, 4000)
        self.assertEqual(settings.max_history, 1)
        self.assertEqual(settings.max_dialogs, 8)

    def test_invalid_limits_are_rejected(self) -> None:
        cases = (
            ("MAX_MESSAGE_LEN", "max_message_len", 0),
            ("MAX_MESSAGE_LEN", "max_message_len", 4001),
            ("MAX_HISTORY", "max_history", 0),
            ("MAX_DIALOGS", "max_dialogs", 0),
            ("MAX_DIALOGS", "max_dialogs", 9),
        )

        for env_name, field, value in cases:
            with self.subTest(env_name=env_name, value=value):
                with self.assertRaisesRegex(ValueError, env_name):
                    make_settings(**{field: value})

    def test_non_integer_environment_limit_is_rejected(self) -> None:
        with (
            patch.dict(os.environ, {"MAX_DIALOGS": "nine"}, clear=True),
            patch("config.settings.load_dotenv"),
            self.assertRaisesRegex(ValueError, "MAX_DIALOGS.*целым числом"),
        ):
            load_settings()


if __name__ == "__main__":
    unittest.main()

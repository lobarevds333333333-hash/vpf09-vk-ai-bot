"""Тесты конфигурации: режимы общения."""

import unittest

from config.settings import MODES


class ModesTest(unittest.TestCase):
    def test_six_modes_with_unique_titles(self) -> None:
        self.assertEqual(len(MODES), 6)
        titles = [mode.title for mode in MODES.values()]
        self.assertEqual(len(set(titles)), 6)
        for mode in MODES.values():
            self.assertTrue(mode.prompt, mode.id)

    def test_python_mentor_mode_exists(self) -> None:
        self.assertEqual(MODES["python_mentor"].title, "Ментор по Python")


if __name__ == "__main__":
    unittest.main()

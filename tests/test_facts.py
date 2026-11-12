"""Тесты сервиса долгосрочных фактов о пользователе."""

import unittest

from models.entities import UserProfile
from services.facts_service import FactsService


def make_user() -> UserProfile:
    return UserProfile(user_id=1, active_dialog_id="main", facts=[], dialogs=[])


class FactsServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FactsService()
        self.user = make_user()

    def test_empty_fact_rejected(self) -> None:
        self.assertIs(self.service.add(self.user, "   "), False)
        self.assertEqual(self.user.facts, [])

    def test_fact_saved_and_truncated(self) -> None:
        self.assertIs(self.service.add(self.user, "а" * 250), True)

        self.assertEqual(len(self.user.facts), 1)
        self.assertEqual(len(self.user.facts[0]), 200)

    def test_duplicate_ignored(self) -> None:
        self.assertIs(self.service.add(self.user, "Люблю кофе"), True)
        self.assertIs(self.service.add(self.user, "  ЛЮБЛЮ КОФЕ  "), False)

        self.assertEqual(len(self.user.facts), 1)

    def test_limit_twenty_facts(self) -> None:
        for index in range(20):
            self.service.add(self.user, f"Факт {index}")

        self.assertIs(self.service.add(self.user, "Двадцать первый"), False)
        self.assertEqual(len(self.user.facts), 20)

    def test_build_block_exact_format(self) -> None:
        self.assertEqual(self.service.build_block(self.user), "")

        self.service.add(self.user, "Любит кофе")
        self.service.add(self.user, "Живёт в Москве")

        self.assertEqual(
            self.service.build_block(self.user),
            "Известные факты о пользователе:\n"
            "- Любит кофе\n"
            "- Живёт в Москве",
        )

    def test_clear_removes_all_facts(self) -> None:
        self.service.add(self.user, "Любит кофе")
        self.service.add(self.user, "Живёт в Москве")

        self.service.clear(self.user)

        self.assertEqual(self.user.facts, [])
        self.assertEqual(self.service.build_block(self.user), "")


if __name__ == "__main__":
    unittest.main()

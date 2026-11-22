"""Поведенческие тесты обработчика обычного текста."""

import tempfile
import unittest
from pathlib import Path
from typing import Any

from bot.handlers import build_labeler
from config.settings import Settings
from services.dialog_service import DialogService
from services.facts_service import FactsService
from storage.user_store import UserStore


class FakeStateDispenser:
    async def delete(self, peer_id: int) -> None:
        return None

    async def set(self, peer_id: int, state: Any, **kwargs: Any) -> None:
        return None


class FakeAIService:
    async def ask(self, *args: Any, **kwargs: Any) -> str:
        raise AssertionError("AI must not be called for an oversized message")


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.from_id = 1
        self.peer_id = 1
        self.from_chat = False
        self.answers: list[str] = []

    def get_payload_json(self) -> dict[str, Any]:
        return {}

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.answers.append(text)


class HandlerInputLimitTest(unittest.IsolatedAsyncioTestCase):
    async def test_remember_command_respects_message_length_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            users_dir = Path(tmp) / "users"
            store = UserStore(users_dir)
            facts = FactsService()
            settings = Settings(
                vk_token="token",
                openrouter_api_key="key",
                openrouter_model="model",
                openrouter_base_url="https://example.invalid/v1",
                max_message_len=100,
                max_history=100,
                max_dialogs=8,
                users_dir=users_dir,
            )
            labeler = build_labeler(
                store=store,
                dialogs=DialogService(store),
                facts=facts,
                ai=FakeAIService(),
                settings=settings,
                state_dispenser=FakeStateDispenser(),
            )
            on_text = labeler.message_view.handlers[-1].handler
            message = FakeMessage("Запомни: " + "а" * 101)

            await on_text(message)

            user = store.load(1)
            self.assertEqual(user.facts, [])
            self.assertEqual(len(message.answers), 1)
            self.assertIn("слишком длинное", message.answers[0])

            valid_message = FakeMessage("Запомни: Любит кофе")
            await on_text(valid_message)

            user = store.load(1)
            self.assertEqual(user.facts, ["Любит кофе"])
            self.assertEqual(len(valid_message.answers), 1)
            self.assertIn("Запомнил: Любит кофе", valid_message.answers[0])


if __name__ == "__main__":
    unittest.main()

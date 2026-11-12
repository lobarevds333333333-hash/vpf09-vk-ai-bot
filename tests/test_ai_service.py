"""Тесты AI-сервиса OpenRouter: контекст, лимит истории, фолбэк."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from config.settings import NO_MARKDOWN_RULE
from models.entities import Message
from services.ai_service import AIService


class AIServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.service = AIService(api_key="test-key", model="test/model")
        self.history = [
            Message(role="user", content="старое сообщение"),
            Message(role="assistant", content="старый ответ"),
        ]

    def test_context_starts_with_system_and_includes_facts(self) -> None:
        facts_block = "Известные факты о пользователе:\n- Любит кофе"

        ctx = self.service.build_context(
            "Ты помощник", facts_block, self.history, "привет"
        )

        self.assertEqual(ctx[0]["role"], "system")
        self.assertIn(facts_block, ctx[0]["content"])
        self.assertIn(NO_MARKDOWN_RULE, ctx[0]["content"])

    def test_history_capped_at_100(self) -> None:
        history = [
            Message(
                role="user" if index % 2 == 0 else "assistant",
                content=f"сообщение {index}",
            )
            for index in range(150)
        ]

        ctx = self.service.build_context("Ты помощник", "", history, "привет")

        self.assertEqual(len(ctx), 102)
        self.assertEqual(ctx[1]["content"], "сообщение 50")
        self.assertEqual(ctx[-2]["content"], "сообщение 149")

    def test_last_message_is_user(self) -> None:
        ctx = self.service.build_context("Ты помощник", "", self.history, "привет")

        self.assertEqual(ctx[-1], {"role": "user", "content": "привет"})

    async def test_success_path_strips_content(self) -> None:
        self.service._client.chat.completions.create = AsyncMock(
            return_value=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="  ответ  ")
                    )
                ]
            )
        )

        answer = await self.service.ask("Ты помощник", "", self.history, "привет")

        self.assertEqual(answer, "ответ")

    async def test_api_error_returns_fallback(self) -> None:
        self.service._client.chat.completions.create = AsyncMock(
            side_effect=Exception("network down")
        )

        with self.assertLogs("services.ai_service", level="ERROR"):
            answer = await self.service.ask(
                "Ты помощник", "", self.history, "привет"
            )

        self.assertEqual(answer, AIService.FALLBACK_TEXT)


if __name__ == "__main__":
    unittest.main()

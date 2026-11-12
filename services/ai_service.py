"""Сервис AI-ответов через OpenRouter с фолбэком при ошибках."""

import logging

from openai import AsyncOpenAI

from config.settings import NO_MARKDOWN_RULE
from models.entities import Message

logger = logging.getLogger(__name__)


class AIService:
    FALLBACK_TEXT = "⚠️ Нейросеть временно недоступна. Попробуйте ещё раз через минуту."

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://openrouter.ai/api/v1",
        max_history: int = 100,
    ):
        self.model = model
        self.max_history = max_history
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    def build_context(
        self,
        system_prompt: str,
        facts_block: str,
        history: list[Message],
        user_text: str,
    ) -> list[dict[str, str]]:
        system_content = system_prompt + "\n\n" + facts_block + "\n\n" + NO_MARKDOWN_RULE
        context: list[dict[str, str]] = [
            {"role": "system", "content": system_content}
        ]
        for message in history[-self.max_history :]:
            context.append({"role": message.role, "content": message.content})
        context.append({"role": "user", "content": user_text})
        return context

    async def ask(
        self,
        system_prompt: str,
        facts_block: str,
        history: list[Message],
        user_text: str,
    ) -> str:
        try:
            context = self.build_context(
                system_prompt, facts_block, history, user_text
            )
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=context,
                max_tokens=1500,
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            logger.error("OpenRouter request failed", exc_info=True)
            return self.FALLBACK_TEXT

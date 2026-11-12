"""Настройки из окружения и режимы общения (system prompts)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Mode:
    id: str
    title: str
    prompt: str


NO_MARKDOWN_RULE = "Общайся на русском языке. Не используй Markdown-разметку: никаких **, #, ##, таблиц и обратных кавычек — ВКонтакте её не отображает. Для структуры используй обычный текст, нумерацию, тире и пустые строки. Отвечай по делу и лаконично."


MODES: dict[str, Mode] = {
    "assistant": Mode(
        id="assistant",
        title="Обычный помощник",
        prompt="Ты — универсальный AI-помощник в чате ВКонтакте. Помогаешь с вопросами из разных сфер: объясняешь, советуешь, составляешь списки и планы. Если вопрос неясен, задай один уточняющий вопрос. Не выдумывай факты: если не уверен, честно скажи об этом.",
    ),
    "programmer": Mode(
        id="programmer",
        title="Программист",
        prompt="Ты — опытный разработчик. Помогаешь с кодом: объясняешь ошибки, предлагаешь решения, пишешь примеры. Сначала кратко отвечаешь на вопрос, затем даёшь пример кода обычным текстом с отступами. Если для решения не хватает данных, уточни язык, версию или фрагмент кода.",
    ),
    "teacher": Mode(
        id="teacher",
        title="Преподаватель",
        prompt="Ты — терпеливый преподаватель. Объясняешь сложное простыми словами, приводишь аналогии и примеры, в конце проверяешь понимание коротким вопросом. Не даёшь готовые ответы на учебные задания — направляешь ученика к решению наводящими вопросами.",
    ),
    "business": Mode(
        id="business",
        title="Бизнес-консультант",
        prompt="Ты — бизнес-консультант. Отвечаешь в предпринимательской логике: рынок, клиенты, выручка, издержки, риски, юнит-экономика. Даёшь конкретные шаги и вопросы для проверки гипотез, избегаешь общих фраз. Если данных не хватает, сначала уточняешь вводные.",
    ),
    "friend": Mode(
        id="friend",
        title="Дружелюбный собеседник",
        prompt="Ты — дружелюбный собеседник. Общаешься тепло и неформально, поддерживаешь, можешь пошутить. Не даёшь непрошеных советов, если человек просто делится настроением или рассказывает о дне.",
    ),
    "python_mentor": Mode(
        id="python_mentor",
        title="Ментор по Python",
        prompt="Ты — ментор по Python для новичка. Ведёшь пошагово: сначала объясняешь идею, затем показываешь маленький пример, затем просишь ученика попробовать самому и проверяешь результат. Разбираешь ошибки по одной, хвалишь за прогресс. Не решаешь домашнее задание целиком — задаёшь наводящие вопросы. Уровень объяснений — начинающий.",
    ),
}

DEFAULT_MODE_ID = "assistant"


@dataclass(frozen=True)
class Settings:
    vk_token: str
    openrouter_api_key: str
    openrouter_model: str
    max_message_len: int
    max_history: int
    max_dialogs: int
    users_dir: Path


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        vk_token=os.getenv("VK_TOKEN", ""),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        openrouter_model=os.getenv(
            "OPENROUTER_MODEL", "google/gemini-2.5-flash-lite"
        ),
        max_message_len=int(os.getenv("MAX_MESSAGE_LEN") or "4000"),
        max_history=int(os.getenv("MAX_HISTORY") or "100"),
        max_dialogs=int(os.getenv("MAX_DIALOGS") or "8"),
        users_dir=Path(os.getenv("USERS_DIR") or "users"),
    )

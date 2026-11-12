"""Точка входа: запуск VK-бота на LongPoll API."""

import logging
import sys

from vkbottle import API, Bot, BuiltinStateDispenser

from bot.handlers import build_labeler
from config.settings import load_settings
from services.ai_service import AIService
from services.dialog_service import DialogService
from services.facts_service import FactsService
from storage.user_store import UserStore

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    if not settings.vk_token:
        logger.error("VK_TOKEN не задан в .env — запуск невозможен")
        sys.exit(1)
    if not settings.openrouter_api_key:
        logger.error("OPENROUTER_API_KEY не задан в .env — запуск невозможен")
        sys.exit(1)

    store = UserStore(settings.users_dir)
    dialogs = DialogService(store, max_dialogs=settings.max_dialogs)
    facts = FactsService()
    ai = AIService(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_model,
        max_history=settings.max_history,
    )
    state_dispenser = BuiltinStateDispenser()
    labeler = build_labeler(store, dialogs, facts, ai, settings, state_dispenser)
    bot = Bot(
        api=API(settings.vk_token),
        labeler=labeler,
        state_dispenser=state_dispenser,
    )
    logger.info("Бот запущен, подключаюсь к LongPoll")
    bot.run()


if __name__ == "__main__":
    main()

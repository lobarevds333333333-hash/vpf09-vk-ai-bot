"""Индикатор «печатает…» в диалоге ВКонтакте."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def typing(api: Any, peer_id: int) -> None:
    try:
        await api.messages.set_activity(type="typing", peer_id=peer_id)
    except Exception:
        # Индикатор необязателен: сбой не должен ломать ответ бота
        logger.warning("Не удалось отправить setActivity", exc_info=True)

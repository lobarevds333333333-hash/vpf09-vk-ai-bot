"""Блокировки по ключу пользователя.

vkbottle 4.11 обрабатывает каждый апдейт отдельной asyncio-задачей, поэтому
два действия одного пользователя могут выполняться параллельно и затирать
друг другу сохранённый профиль. UserLocks даёт одну asyncio.Lock на ключ
(peer_id), сериализуя read-modify-write внутри обработчиков.
"""

import asyncio


class UserLocks:
    def __init__(self) -> None:
        self._locks: dict[int, asyncio.Lock] = {}

    def get(self, key: int) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = self._locks[key] = asyncio.Lock()
        return lock

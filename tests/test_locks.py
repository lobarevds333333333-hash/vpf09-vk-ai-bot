"""Тесты пользовательских блокировок: сериализация по ключу peer_id."""

import asyncio
import unittest

from utils.locks import UserLocks


class UserLocksTest(unittest.IsolatedAsyncioTestCase):
    def test_get_returns_same_lock_for_same_key(self) -> None:
        locks = UserLocks()

        self.assertIs(locks.get(5), locks.get(5))
        self.assertIsNot(locks.get(5), locks.get(6))

    async def test_same_key_does_not_interleave(self) -> None:
        locks = UserLocks()
        events: list[str] = []
        first_inside = asyncio.Event()

        async def first() -> None:
            async with locks.get(1):
                events.append("first_start")
                first_inside.set()
                await asyncio.sleep(0.05)
                events.append("first_end")

        async def second() -> None:
            await first_inside.wait()
            async with locks.get(1):
                events.append("second_start")
                events.append("second_end")

        await asyncio.gather(first(), second())

        self.assertEqual(
            events,
            ["first_start", "first_end", "second_start", "second_end"],
        )


if __name__ == "__main__":
    unittest.main()

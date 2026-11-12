"""Сервис долгосрочных фактов о пользователе.

Сервис меняет переданный UserProfile в памяти и не сохраняет его —
сохранение выполняет вызывающий код (обработчик) один раз.
"""

from models.entities import UserProfile

MAX_FACTS = 20
MAX_FACT_LENGTH = 200


class FactsService:
    def add(self, user: UserProfile, text: str) -> bool:
        fact = text.strip()[:MAX_FACT_LENGTH]
        if not fact:
            return False
        if len(user.facts) >= MAX_FACTS:
            return False
        lowered = fact.lower()
        if any(existing.lower() == lowered for existing in user.facts):
            return False
        user.facts.append(fact)
        return True

    def clear(self, user: UserProfile) -> None:
        user.facts.clear()

    def build_block(self, user: UserProfile) -> str:
        if not user.facts:
            return ""
        return "Известные факты о пользователе:\n- " + "\n- ".join(user.facts)

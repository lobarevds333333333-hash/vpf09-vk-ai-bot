"""Обработчики сообщений ВК: меню, диалоги, режимы, факты и AI-ответы."""

import logging
from typing import Any

from vkbottle import ABCStateDispenser, BaseStateGroup
from vkbottle.bot import BotLabeler, Message

from config.settings import MODES, Settings
from keyboards.menus import (
    dialogs_menu,
    facts_menu,
    main_menu,
    modes_menu,
    settings_menu,
)
from models.entities import Dialog, Message as ChatMessage, UserProfile
from services.ai_service import AIService
from services.dialog_service import DialogService
from services.facts_service import MAX_FACT_LENGTH, MAX_FACTS, FactsService
from storage.user_store import UserStore
from utils.typing import typing

logger = logging.getLogger(__name__)

REMEMBER_PREFIX = "запомни:"

HELP_TEXT = (
    "❓ Помощь\n"
    "Просто напишите вопрос — я отвечу в активном диалоге.\n"
    "🆕 Новый диалог — начать с чистого контекста.\n"
    "📋 Мои диалоги — переключение, переименование и удаление.\n"
    "🎭 Сменить режим — выбрать одну из шести ролей общения.\n"
    "🧠 Факты обо мне — что бот помнит о вас.\n"
    "⚙️ Настройки — текущая модель и очистка истории.\n"
    "Чтобы запомнить факт, напишите: Запомни: <текст>."
)


class RenameState(BaseStateGroup):
    WAIT_NAME = "rename_wait_name"


def build_labeler(
    store: UserStore,
    dialogs: DialogService,
    facts: FactsService,
    ai: AIService,
    settings: Settings,
    state_dispenser: ABCStateDispenser,
) -> BotLabeler:
    labeler = BotLabeler()

    def user_of(message: Message) -> UserProfile:
        return store.ensure_user(message.from_id)

    def active_dialog(user: UserProfile) -> Dialog:
        try:
            return dialogs.get_active(user)
        except ValueError:
            fallback = user.dialogs[0]
            logger.warning(
                "У пользователя %s активный диалог %s не найден — переключаюсь на %s",
                user.user_id,
                user.active_dialog_id,
                fallback.id,
            )
            user.active_dialog_id = fallback.id
            return fallback

    def find_dialog(user: UserProfile, dialog_id: Any) -> Dialog | None:
        for dialog in user.dialogs:
            if dialog.id == dialog_id:
                return dialog
        return None

    def payload_of(message: Message) -> dict[str, Any]:
        payload = message.get_payload_json()
        return payload if isinstance(payload, dict) else {}

    def facts_text(user: UserProfile) -> str:
        return "🧠 Факты обо мне:\n- " + "\n- ".join(user.facts)

    async def remember_fact(message: Message, user: UserProfile, fact_text: str) -> None:
        if facts.add(user, fact_text):
            store.save(user)
            await message.answer(
                "Запомнил: " + user.facts[-1] + "\n\n" + facts_text(user),
                keyboard=facts_menu(True).get_json(),
            )
            return

        if not fact_text:
            reason = "После «Запомни:» нет текста. Напишите: Запомни: <факт>."
        elif len(user.facts) >= MAX_FACTS:
            reason = (
                f"Достигнут лимит в {MAX_FACTS} фактов. "
                "Очистите список в разделе «🧠 Факты обо мне»."
            )
        elif any(
            existing.lower() == fact_text[:MAX_FACT_LENGTH].lower()
            for existing in user.facts
        ):
            reason = "Такой факт уже сохранён."
        else:
            reason = "Не удалось сохранить факт."
        await message.answer(
            reason, keyboard=facts_menu(bool(user.facts)).get_json()
        )

    @labeler.message(payload={"cmd": "new_dialog"})
    async def on_new_dialog(message: Message) -> None:
        user = user_of(message)
        dialog = dialogs.create(user)
        store.save(user)
        await message.answer(
            f"Создан диалог «{dialog.title}».\n"
            f"Режим: {MODES[dialog.mode_id].title}.\n"
            "Напишите сообщение — я отвечу.",
            keyboard=main_menu().get_json(),
        )

    @labeler.message(payload={"cmd": "dialogs"})
    async def on_dialogs(message: Message) -> None:
        user = user_of(message)
        active = active_dialog(user)
        store.save(user)
        await message.answer(
            f"Ваши диалоги: {len(user.dialogs)}.\n"
            f"Активный — «{active.title}».\n"
            "Нажмите на диалог, чтобы переключиться.",
            keyboard=dialogs_menu(user.dialogs, active.id).get_json(),
        )

    @labeler.message(payload_contains={"cmd": "switch"})
    async def on_switch(message: Message) -> None:
        user = user_of(message)
        dialog = find_dialog(user, payload_of(message).get("id"))
        if dialog is None:
            await message.answer(
                "Диалог не найден", keyboard=main_menu().get_json()
            )
            return
        dialogs.switch(user, dialog.id)
        store.save(user)
        await message.answer(
            f"Активный диалог — «{dialog.title}».\n"
            f"Режим: {MODES[dialog.mode_id].title}.",
            keyboard=main_menu().get_json(),
        )

    @labeler.message(payload_contains={"cmd": "rename"})
    async def on_rename(message: Message) -> None:
        user = user_of(message)
        dialog = find_dialog(user, payload_of(message).get("id"))
        if dialog is None:
            await message.answer(
                "Диалог не найден", keyboard=main_menu().get_json()
            )
            return
        await state_dispenser.set(
            message.peer_id, RenameState.WAIT_NAME, dialog_id=dialog.id
        )
        await message.answer(
            f"Введите новое название для диалога «{dialog.title}» "
            "или отправьте «Отмена»."
        )

    @labeler.message(payload_contains={"cmd": "delete"})
    async def on_delete(message: Message) -> None:
        user = user_of(message)
        dialog = find_dialog(user, payload_of(message).get("id"))
        if dialog is None:
            await message.answer(
                "Диалог не найден", keyboard=main_menu().get_json()
            )
            return
        if len(user.dialogs) <= 1:
            await message.answer(
                "Нельзя удалить единственный диалог",
                keyboard=main_menu().get_json(),
            )
            return
        deleted_title = dialog.title
        dialogs.delete(user, dialog.id)
        store.save(user)
        active = active_dialog(user)
        await message.answer(
            f"Диалог «{deleted_title}» удалён.\n"
            f"Активный диалог — «{active.title}».",
            keyboard=main_menu().get_json(),
        )

    @labeler.message(payload={"cmd": "modes"})
    async def on_modes(message: Message) -> None:
        user = user_of(message)
        active = active_dialog(user)
        store.save(user)
        await message.answer(
            f"Выберите режим для диалога «{active.title}».\n"
            f"Сейчас активен: {MODES[active.mode_id].title}.",
            keyboard=modes_menu(active.mode_id).get_json(),
        )

    @labeler.message(payload_contains={"cmd": "mode"})
    async def on_mode(message: Message) -> None:
        user = user_of(message)
        active = active_dialog(user)
        mode_id = payload_of(message).get("id")
        if mode_id not in MODES:
            await message.answer(
                "Режим не найден.",
                keyboard=modes_menu(active.mode_id).get_json(),
            )
            return
        dialogs.set_mode(user, active.id, mode_id)
        store.save(user)
        await message.answer(
            f"Режим «{MODES[mode_id].title}» применён к диалогу «{active.title}».",
            keyboard=modes_menu(mode_id).get_json(),
        )

    @labeler.message(payload={"cmd": "settings"})
    async def on_settings(message: Message) -> None:
        user = user_of(message)
        active = active_dialog(user)
        store.save(user)
        await message.answer(
            "⚙️ Настройки\n"
            f"Модель: {settings.openrouter_model}\n"
            f"Активный диалог: «{active.title}»\n"
            f"Режим: {MODES[active.mode_id].title}\n"
            f"Сообщений в истории: {len(active.messages)}",
            keyboard=settings_menu().get_json(),
        )

    @labeler.message(payload={"cmd": "clear_history"})
    async def on_clear_history(message: Message) -> None:
        user = user_of(message)
        active = active_dialog(user)
        dialogs.clear_history(user, active.id)
        store.save(user)
        await message.answer(
            f"История диалога «{active.title}» очищена.",
            keyboard=main_menu().get_json(),
        )

    @labeler.message(payload={"cmd": "facts"})
    async def on_facts(message: Message) -> None:
        user = user_of(message)
        if user.facts:
            text = facts_text(user) + "\n\nДобавить факт: Запомни: <текст>."
        else:
            text = (
                "Пока нет сохранённых фактов.\n"
                "Чтобы запомнить факт, напишите: Запомни: <текст>."
            )
        await message.answer(
            text, keyboard=facts_menu(bool(user.facts)).get_json()
        )

    @labeler.message(payload={"cmd": "facts_clear"})
    async def on_facts_clear(message: Message) -> None:
        user = user_of(message)
        facts.clear(user)
        store.save(user)
        await message.answer(
            "Все факты удалены.", keyboard=facts_menu(False).get_json()
        )

    @labeler.message(payload={"cmd": "help"})
    async def on_help(message: Message) -> None:
        await message.answer(HELP_TEXT, keyboard=main_menu().get_json())

    @labeler.message(payload={"cmd": "back"})
    async def on_back(message: Message) -> None:
        await message.answer("Главное меню.", keyboard=main_menu().get_json())

    @labeler.message(state=RenameState.WAIT_NAME)
    async def on_rename_name(message: Message) -> None:
        user = user_of(message)
        new_title = (message.text or "").strip()
        await state_dispenser.delete(message.peer_id)
        if new_title.lower() == "отмена":
            await message.answer(
                "Переименование отменено.", keyboard=main_menu().get_json()
            )
            return
        dialog_id = (
            message.state_peer.payload.get("dialog_id")
            if message.state_peer
            else None
        )
        dialog = find_dialog(user, dialog_id)
        if dialog is None:
            await message.answer(
                "Диалог не найден", keyboard=main_menu().get_json()
            )
            return
        if not new_title:
            await message.answer(
                "Пустое название — имя диалога не изменено.",
                keyboard=main_menu().get_json(),
            )
            return
        dialogs.rename(user, dialog.id, new_title)
        store.save(user)
        await message.answer(
            f"Диалог переименован в «{dialog.title}».",
            keyboard=main_menu().get_json(),
        )

    @labeler.message()
    async def on_text(message: Message) -> None:
        user = user_of(message)
        text = (message.text or "").strip()
        if not text:
            await message.answer(
                "Напишите текстовое сообщение — я отвечу.",
                keyboard=main_menu().get_json(),
            )
            return

        if text.lower().startswith(REMEMBER_PREFIX):
            await remember_fact(
                message, user, text[len(REMEMBER_PREFIX):].strip()
            )
            return

        if len(text) > settings.max_message_len:
            await message.answer(
                f"Сообщение слишком длинное: {len(text)} символов "
                f"при лимите {settings.max_message_len}. "
                "Сократите текст и попробуйте снова.",
                keyboard=main_menu().get_json(),
            )
            return

        active = active_dialog(user)
        await typing(message.ctx_api, message.peer_id)
        reply = await ai.ask(
            MODES[active.mode_id].prompt,
            facts.build_block(user),
            active.messages,
            text,
        )
        if not reply or not reply.strip():
            reply = AIService.FALLBACK_TEXT
        active.messages.append(ChatMessage(role="user", content=text))
        active.messages.append(ChatMessage(role="assistant", content=reply))
        if len(active.messages) > settings.max_history:
            del active.messages[: len(active.messages) - settings.max_history]
        store.save(user)
        await message.answer(reply, keyboard=main_menu().get_json())

    return labeler

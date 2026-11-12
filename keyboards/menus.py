"""Сборка клавиатур. Payload кнопок: {"cmd": "..."} или {"cmd": ..., "id": "..."}."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from config.settings import MODES
from models.entities import Dialog

MAX_BUTTON_LABEL = 40


def _fit(label: str) -> str:
    """Обрезает готовую подпись кнопки под лимит ВК в 40 символов."""
    if len(label) <= MAX_BUTTON_LABEL:
        return label
    return label[: MAX_BUTTON_LABEL - 1] + "…"


def _cmd(command: str) -> dict[str, str]:
    return {"cmd": command}


def _cmd_id(command: str, item_id: str) -> dict[str, str]:
    return {"cmd": command, "id": item_id}


def main_menu() -> Keyboard:
    keyboard = Keyboard(inline=True)
    keyboard.add(
        Text("🆕 Новый диалог", payload=_cmd("new_dialog")),
        color=KeyboardButtonColor.POSITIVE,
    )
    keyboard.add(Text("📋 Мои диалоги", payload=_cmd("dialogs")))
    keyboard.row()
    keyboard.add(Text("🎭 Сменить режим", payload=_cmd("modes")))
    keyboard.add(Text("🧠 Факты обо мне", payload=_cmd("facts")))
    keyboard.row()
    keyboard.add(Text("⚙️ Настройки", payload=_cmd("settings")))
    keyboard.add(Text("❓ Помощь", payload=_cmd("help")))
    return keyboard


def dialogs_menu(dialogs: list[Dialog], active_id: str) -> Keyboard:
    # inline-клавиатура ВК: не больше 6 рядов; диалоги — по 2 в ряд.
    # При 8 диалогах: 4 ряда + 2 ряда действий = 6.
    keyboard = Keyboard(inline=True)
    for index, dialog in enumerate(dialogs):
        title = "✅ " + dialog.title if dialog.id == active_id else dialog.title
        keyboard.add(Text(_fit(title), payload=_cmd_id("switch", dialog.id)))
        if index % 2 == 1:
            keyboard.row()
    if len(dialogs) % 2 == 1:
        keyboard.row()
    keyboard.add(
        Text("✏️ Переименовать", payload=_cmd_id("rename", active_id)),
        color=KeyboardButtonColor.PRIMARY,
    )
    keyboard.add(
        Text("🗑 Удалить", payload=_cmd_id("delete", active_id)),
        color=KeyboardButtonColor.NEGATIVE,
    )
    keyboard.row()
    keyboard.add(
        Text("🆕 Новый", payload=_cmd("new_dialog")),
        color=KeyboardButtonColor.POSITIVE,
    )
    keyboard.add(Text("◀️ Назад", payload=_cmd("back")))
    return keyboard


def modes_menu(current: str) -> Keyboard:
    keyboard = Keyboard(inline=True)
    modes = list(MODES.values())
    for index, mode in enumerate(modes):
        title = "✅ " + mode.title if mode.id == current else mode.title
        keyboard.add(Text(_fit(title), payload=_cmd_id("mode", mode.id)))
        if index % 2 == 1:
            keyboard.row()
    if len(modes) % 2 == 1:
        keyboard.row()
    keyboard.add(Text("◀️ Назад", payload=_cmd("back")))
    return keyboard


def settings_menu() -> Keyboard:
    keyboard = Keyboard(inline=True)
    keyboard.add(
        Text("🧹 Очистить историю", payload=_cmd("clear_history")),
        color=KeyboardButtonColor.NEGATIVE,
    )
    keyboard.row()
    keyboard.add(Text("◀️ Назад", payload=_cmd("back")))
    return keyboard


def facts_menu(has_facts: bool) -> Keyboard:
    keyboard = Keyboard(inline=True)
    if has_facts:
        keyboard.add(
            Text("🗑 Очистить факты", payload=_cmd("facts_clear")),
            color=KeyboardButtonColor.NEGATIVE,
        )
        keyboard.row()
    keyboard.add(Text("◀️ Назад", payload=_cmd("back")))
    return keyboard

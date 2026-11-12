"""Сервис диалогов: CRUD диалогов внутри профиля пользователя.

Сервис меняет переданный UserProfile в памяти и не сохраняет его —
сохранение выполняет вызывающий код (обработчик) один раз.
"""

import uuid

from config.settings import DEFAULT_MODE_ID, MODES
from models.entities import Dialog, UserProfile
from storage.user_store import UserStore


class DialogService:
    def __init__(self, store: UserStore):
        self.store = store

    def _find(self, user: UserProfile, dialog_id: str) -> Dialog:
        for dialog in user.dialogs:
            if dialog.id == dialog_id:
                return dialog
        raise ValueError(f"Unknown dialog: {dialog_id}")

    def get_active(self, user: UserProfile) -> Dialog:
        return self._find(user, user.active_dialog_id)

    def create(self, user: UserProfile, title: str | None = None) -> Dialog:
        dialog = Dialog(
            id=uuid.uuid4().hex[:8],
            title=title if title is not None else f"Диалог {len(user.dialogs) + 1}",
            mode_id=DEFAULT_MODE_ID,
            messages=[],
        )
        user.dialogs.append(dialog)
        user.active_dialog_id = dialog.id
        return dialog

    def switch(self, user: UserProfile, dialog_id: str) -> Dialog:
        dialog = self._find(user, dialog_id)
        user.active_dialog_id = dialog.id
        return dialog

    def rename(self, user: UserProfile, dialog_id: str, new_title: str) -> Dialog:
        dialog = self._find(user, dialog_id)
        title = new_title.strip()
        if title:
            dialog.title = title
        return dialog

    def delete(self, user: UserProfile, dialog_id: str) -> bool:
        if len(user.dialogs) <= 1:
            return False
        for index, dialog in enumerate(user.dialogs):
            if dialog.id != dialog_id:
                continue
            del user.dialogs[index]
            if user.active_dialog_id == dialog_id:
                user.active_dialog_id = user.dialogs[0].id
            return True
        return False

    def set_mode(self, user: UserProfile, dialog_id: str, mode_id: str) -> Dialog:
        dialog = self._find(user, dialog_id)
        if mode_id not in MODES:
            raise ValueError(f"Unknown mode: {mode_id}")
        dialog.mode_id = mode_id
        return dialog

    def clear_history(self, user: UserProfile, dialog_id: str) -> None:
        dialog = self._find(user, dialog_id)
        dialog.messages.clear()

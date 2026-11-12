"""Файловое JSON-хранилище профилей: users/<user_id>.json."""

import json
import logging
import os
from pathlib import Path

from models.entities import Dialog, UserProfile

logger = logging.getLogger(__name__)


def _default_dialog() -> Dialog:
    return Dialog(id="main", title="Основной", mode_id="assistant", messages=[])


def _default_profile(user_id: int) -> UserProfile:
    return UserProfile(
        user_id=user_id,
        active_dialog_id="main",
        facts=[],
        dialogs=[_default_dialog()],
    )


def _repair(user: UserProfile) -> None:
    """Чинит профиль, загруженный из JSON, не разрушая данные пользователя."""
    if not user.dialogs:
        user.dialogs.append(_default_dialog())
        logger.warning(
            "Профиль пользователя %s: пустой список диалогов — создан «Основной»",
            user.user_id,
        )
    if all(dialog.id != user.active_dialog_id for dialog in user.dialogs):
        user.active_dialog_id = user.dialogs[0].id
        logger.warning(
            "Профиль пользователя %s: активный диалог не найден — выбран %s",
            user.user_id,
            user.active_dialog_id,
        )


class UserStore:
    def __init__(self, users_dir: Path):
        self.users_dir = Path(users_dir)

    def _path(self, user_id: int) -> Path:
        return self.users_dir / f"{user_id}.json"

    def ensure_user(self, user_id: int) -> UserProfile:
        if self._path(user_id).exists():
            return self.load(user_id)
        user = _default_profile(user_id)
        self.save(user)
        return user

    def load(self, user_id: int) -> UserProfile:
        path = self._path(user_id)
        if not path.exists():
            return _default_profile(user_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            user = UserProfile.from_dict(data)
        except (
            json.JSONDecodeError,
            UnicodeDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            # Битый файл сохраняем как .bak — данные не удаляем
            backup = path.with_name(path.name + ".bak")
            os.replace(path, backup)
            logger.warning(
                "Файл пользователя %s повреждён (%s) — сохранён как %s, "
                "возвращён профиль по умолчанию",
                user_id,
                error,
                backup.name,
            )
            return _default_profile(user_id)
        _repair(user)
        return user

    def save(self, user: UserProfile) -> None:
        self.users_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "posix":
            # mkdir не ужимает уже существующий каталог — пробуем явно
            try:
                os.chmod(self.users_dir, 0o700)
            except OSError:
                pass
        path = self._path(user.user_id)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            json.dumps(user.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

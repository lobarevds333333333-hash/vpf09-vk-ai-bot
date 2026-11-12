"""Файловое JSON-хранилище профилей: users/<user_id>.json."""

import json
import os
from pathlib import Path

from models.entities import Dialog, UserProfile


def _default_profile(user_id: int) -> UserProfile:
    return UserProfile(
        user_id=user_id,
        active_dialog_id="main",
        facts=[],
        dialogs=[
            Dialog(id="main", title="Основной", mode_id="assistant", messages=[]),
        ],
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
        except json.JSONDecodeError:
            # Битый файл сохраняем как .bak — данные не удаляем
            os.replace(path, path.with_name(path.name + ".bak"))
            return _default_profile(user_id)
        return UserProfile.from_dict(data)

    def save(self, user: UserProfile) -> None:
        self.users_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(user.user_id)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            json.dumps(user.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, path)

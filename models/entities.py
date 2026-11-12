"""Модели данных бота: сообщение, диалог, профиль пользователя."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Message:
    role: str
    content: str
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data["timestamp"],
        )


@dataclass
class Dialog:
    id: str
    title: str
    mode_id: str
    messages: list[Message]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "mode_id": self.mode_id,
            "messages": [message.to_dict() for message in self.messages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Dialog":
        return cls(
            id=data["id"],
            title=data["title"],
            mode_id=data["mode_id"],
            messages=[Message.from_dict(item) for item in data.get("messages", [])],
        )


@dataclass
class UserProfile:
    user_id: int
    active_dialog_id: str
    facts: list[str]
    dialogs: list[Dialog]

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "active_dialog_id": self.active_dialog_id,
            "facts": list(self.facts),
            "dialogs": [dialog.to_dict() for dialog in self.dialogs],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserProfile":
        return cls(
            user_id=int(data["user_id"]),
            active_dialog_id=data["active_dialog_id"],
            facts=list(data.get("facts", [])),
            dialogs=[Dialog.from_dict(item) for item in data.get("dialogs", [])],
        )

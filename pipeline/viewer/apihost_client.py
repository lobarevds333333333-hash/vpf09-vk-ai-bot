"""Минимальный клиент ApiHost Responses без утечки секрета в вывод."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


APIHOST_RESPONSES_URL = "https://api.apihost.one/v1/responses"
VIEWER_MODEL = "claude-opus-5.5"
VIEWER_REASONING_EFFORT = "high"
VIEWER_SCHEMA_PATH = Path(__file__).with_name("verdict.schema.json")


def load_viewer_schema() -> dict[str, Any]:
    schema = json.loads(VIEWER_SCHEMA_PATH.read_text("utf-8"))
    schema.pop("$schema", None)
    schema.pop("$id", None)
    return schema


class ApiHostError(RuntimeError):
    """ApiHost недоступен или вернул непригодный ответ."""


class ApiHostClient:
    """Выполняет один запрос к Responses API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str = APIHOST_RESPONSES_URL,
        default_timeout_seconds: int = 180,
    ) -> None:
        resolved_key = api_key if api_key is not None else os.environ.get("APIHOST_API_KEY")
        if not resolved_key:
            raise ApiHostError("APIHOST_API_KEY не задан в environment")
        self._api_key = resolved_key
        self._endpoint = endpoint
        self._default_timeout_seconds = default_timeout_seconds

    def review(
        self,
        *,
        instructions: str,
        prompt: str,
        timeout_seconds: int | None = None,
    ) -> str:
        payload = {
            "model": VIEWER_MODEL,
            "instructions": instructions,
            "input": prompt,
            "reasoning": {"effort": VIEWER_REASONING_EFFORT},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "viewer_verdict",
                    "schema": load_viewer_schema(),
                    "strict": True,
                }
            },
            "max_output_tokens": 12000,
            "store": False,
        }
        request = Request(
            self._endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        timeout = timeout_seconds or self._default_timeout_seconds
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
        except HTTPError as error:
            raise ApiHostError(f"ApiHost вернул HTTP {error.code}") from None
        except (TimeoutError, socket.timeout):
            raise ApiHostError("ApiHost не ответил до таймаута") from None
        except URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise ApiHostError("ApiHost не ответил до таймаута") from None
            raise ApiHostError("Не удалось подключиться к ApiHost") from None
        except UnicodeError:
            raise ApiHostError("ApiHost вернул ответ в неизвестной кодировке") from None

        try:
            response_data = json.loads(body)
        except json.JSONDecodeError:
            raise ApiHostError("ApiHost вернул невалидный JSON") from None
        return _extract_output_text(response_data)


def _extract_output_text(response_data: Any) -> str:
    if not isinstance(response_data, dict):
        raise ApiHostError("ApiHost вернул JSON неверной структуры")

    output_text = response_data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    for item in response_data.get("output", []):
        if not isinstance(item, dict):
            continue
        for part in item.get("content", []):
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                return text
    raise ApiHostError("ApiHost не вернул текст review")

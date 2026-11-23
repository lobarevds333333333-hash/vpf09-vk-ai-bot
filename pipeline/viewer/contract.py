"""Проверка структуры вердикта независимого вьювера."""

from __future__ import annotations

import re
from typing import Any


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
VERDICTS = {"PASS", "PASS_WITH_RISKS", "FAIL"}
SEVERITIES = {"P0", "P1", "P2", "P3"}
TOP_LEVEL_FIELDS = {
    "reviewed_sha",
    "verdict",
    "evidence",
    "findings",
    "limitations",
}
FINDING_FIELDS = {"severity", "path", "line", "evidence", "action"}


class ContractError(ValueError):
    """Вердикт не соответствует каноническому контракту."""


def _require_non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} должен быть непустой строкой")
    return value


def _require_string_list(value: Any, field: str, *, minimum: int = 0) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ContractError(f"{field} должен быть массивом минимум из {minimum} строк")
    for index, item in enumerate(value):
        _require_non_empty_string(item, f"{field}[{index}]")
    return value


def validate_verdict(data: Any) -> dict[str, Any]:
    """Проверяет вердикт и возвращает его без преобразования."""
    if not isinstance(data, dict):
        raise ContractError("вердикт должен быть JSON-объектом")
    missing = sorted(TOP_LEVEL_FIELDS - data.keys())
    extra = sorted(data.keys() - TOP_LEVEL_FIELDS)
    if missing:
        raise ContractError(f"отсутствуют обязательные поля: {', '.join(missing)}")
    if extra:
        raise ContractError(f"неизвестные поля: {', '.join(extra)}")

    reviewed_sha = _require_non_empty_string(data["reviewed_sha"], "reviewed_sha")
    if not SHA_PATTERN.fullmatch(reviewed_sha):
        raise ContractError("reviewed_sha должен быть полным 40-символьным SHA")

    verdict = _require_non_empty_string(data["verdict"], "verdict")
    if verdict not in VERDICTS:
        raise ContractError("verdict должен быть PASS, PASS_WITH_RISKS или FAIL")

    _require_string_list(data["evidence"], "evidence", minimum=1)
    _require_string_list(data["limitations"], "limitations")
    findings = data["findings"]
    if not isinstance(findings, list):
        raise ContractError("findings должен быть массивом")

    for index, finding in enumerate(findings):
        prefix = f"findings[{index}]"
        if not isinstance(finding, dict):
            raise ContractError(f"{prefix} должен быть объектом")
        missing_fields = sorted(FINDING_FIELDS - finding.keys())
        extra_fields = sorted(finding.keys() - FINDING_FIELDS)
        if missing_fields:
            raise ContractError(
                f"{prefix}: отсутствуют поля {', '.join(missing_fields)}"
            )
        if extra_fields:
            raise ContractError(f"{prefix}: неизвестные поля {', '.join(extra_fields)}")
        if finding["severity"] not in SEVERITIES:
            raise ContractError(f"{prefix}.severity должен быть P0–P3")
        _require_non_empty_string(finding["path"], f"{prefix}.path")
        if not isinstance(finding["line"], int) or isinstance(finding["line"], bool):
            raise ContractError(f"{prefix}.line должен быть целым числом")
        if finding["line"] < 1:
            raise ContractError(f"{prefix}.line должен быть положительным")
        _require_non_empty_string(finding["evidence"], f"{prefix}.evidence")
        _require_non_empty_string(finding["action"], f"{prefix}.action")

    if verdict == "PASS" and findings:
        raise ContractError("PASS не может содержать findings")
    if verdict == "PASS_WITH_RISKS" and any(
        finding["severity"] != "P3" for finding in findings
    ):
        raise ContractError("PASS_WITH_RISKS допускает только findings P3")
    return data

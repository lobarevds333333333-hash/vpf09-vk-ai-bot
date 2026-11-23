"""Создаёт Check Run для точного PR head SHA."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pipeline.viewer.contract import ContractError, validate_verdict


CHECK_NAME = "Independent Viewer (Claude Opus 5.5)"
API_ROOT = "https://api.github.com"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
RequestJson = Callable[[str, str, dict[str, Any]], Any]


class CheckError(RuntimeError):
    """Check Run не удалось опубликовать."""


def _request_json(method: str, url: str, payload: dict[str, Any]) -> Any:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise CheckError("GITHUB_TOKEN не задан")
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "vpf09-viewer-check",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as error:
        raise CheckError(f"GitHub API вернул HTTP {error.code}") from None
    except (TimeoutError, URLError):
        raise CheckError("GitHub API недоступен") from None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise CheckError("GitHub API вернул невалидный JSON") from None


def load_check_result(
    *,
    verdict_path: Path,
    summary_path: Path,
    expected_sha: str,
) -> tuple[str, str, str]:
    try:
        verdict = json.loads(verdict_path.read_text("utf-8"))
        validate_verdict(verdict)
        if verdict["reviewed_sha"] != expected_sha:
            raise ContractError("reviewed_sha не совпадает с head SHA")
        summary = summary_path.read_text("utf-8")
        result = verdict["verdict"]
        conclusion = "success" if result == "PASS" else "failure"
        return result, conclusion, summary
    except (OSError, json.JSONDecodeError, ContractError):
        return (
            "FAIL",
            "failure",
            "Independent Viewer не создал contract-valid verdict; merge заблокирован.",
        )


def publish_check(
    *,
    repository: str,
    head_sha: str,
    result: str,
    conclusion: str,
    summary: str,
    details_url: str | None,
    request_json: RequestJson = _request_json,
) -> int:
    if "/" not in repository:
        raise CheckError("repository должен иметь формат owner/repo")
    if not FULL_SHA.fullmatch(head_sha):
        raise CheckError("head_sha должен быть полным 40-символьным SHA")
    if conclusion not in {"success", "failure"}:
        raise CheckError("conclusion должен быть success или failure")
    payload: dict[str, Any] = {
        "name": CHECK_NAME,
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": conclusion,
        "output": {
            "title": f"Independent Viewer: {result}",
            "summary": summary[:60_000],
        },
    }
    if details_url:
        payload["details_url"] = details_url
    response = request_json(
        "POST",
        f"{API_ROOT}/repos/{repository}/check-runs",
        payload,
    )
    if not isinstance(response, dict) or not isinstance(response.get("id"), int):
        raise CheckError("GitHub API не вернул ID Check Run")
    return response["id"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--verdict-path", type=Path, required=True)
    parser.add_argument("--summary-path", type=Path, required=True)
    parser.add_argument("--details-url")
    args = parser.parse_args(argv)
    result, conclusion, summary = load_check_result(
        verdict_path=args.verdict_path,
        summary_path=args.summary_path,
        expected_sha=args.head_sha,
    )
    try:
        check_id = publish_check(
            repository=args.repository,
            head_sha=args.head_sha,
            result=result,
            conclusion=conclusion,
            summary=summary,
            details_url=args.details_url,
        )
    except CheckError as error:
        print(f"Viewer check failed: {error}", file=sys.stderr)
        return 1
    print(f"Viewer check published: {check_id} ({conclusion})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

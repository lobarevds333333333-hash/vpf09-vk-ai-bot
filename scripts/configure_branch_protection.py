"""Настраивает fail-closed branch protection для main через GitHub API."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_ROOT = "https://api.github.com"
REQUIRED_CHECKS = (
    "Python 3.11 on ubuntu-latest",
    "Python 3.11 on windows-latest",
    "PR Agent review",
    "Independent Viewer (Claude Opus 5.5)",
)


class ProtectionError(RuntimeError):
    """Branch protection не удалось обновить или проверить."""


def build_payload() -> dict[str, Any]:
    return {
        "required_status_checks": {
            "strict": True,
            "checks": [{"context": context} for context in REQUIRED_CHECKS],
        },
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
            "required_approving_review_count": 0,
            "require_last_push_approval": False,
        },
        "restrictions": None,
        "required_conversation_resolution": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "lock_branch": False,
        "allow_fork_syncing": False,
    }


def _read_token() -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ProtectionError("GitHub token недоступен") from None
    token = result.stdout.strip()
    if result.returncode != 0 or not token:
        raise ProtectionError("GitHub token недоступен; задайте GITHUB_TOKEN")
    return token


def apply_protection(*, repository: str, branch: str, payload: dict[str, Any]) -> dict[str, Any]:
    if "/" not in repository:
        raise ProtectionError("repository должен иметь формат owner/repo")
    request = Request(
        f"{API_ROOT}/repos/{repository}/branches/{branch}/protection",
        data=json.dumps(payload).encode("utf-8"),
        method="PUT",
        headers={
            "Authorization": f"Bearer {_read_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "vpf09-branch-protection",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as error:
        raise ProtectionError(f"GitHub API вернул HTTP {error.code}") from None
    except (TimeoutError, URLError):
        raise ProtectionError("GitHub API недоступен") from None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise ProtectionError("GitHub API вернул невалидный JSON") from None
    if not isinstance(parsed, dict):
        raise ProtectionError("GitHub API вернул ответ неверной структуры")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="owner/repo")
    parser.add_argument("--branch", default="main")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    payload = build_payload()
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    try:
        response = apply_protection(
            repository=args.repository,
            branch=args.branch,
            payload=payload,
        )
    except ProtectionError as error:
        print(f"Branch protection failed: {error}", file=sys.stderr)
        return 1
    contexts = [
        check.get("context")
        for check in response.get("required_status_checks", {}).get("checks", [])
        if isinstance(check, dict)
    ]
    print(f"Branch protection applied: {args.repository}:{args.branch}")
    print(f"Required checks: {', '.join(context for context in contexts if context)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Обновляет единственный PR-комментарий с результатом вьювера."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


COMMENT_MARKER = "<!-- independent-viewer-verdict -->"
API_ROOT = "https://api.github.com"
MAX_COMMENT_LENGTH = 60_000
RequestJson = Callable[[str, str, dict[str, Any] | None], Any]


class GitHubApiError(RuntimeError):
    """GitHub API не позволил обновить summary."""


def _request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise GitHubApiError("GITHUB_TOKEN не задан")
    request = Request(
        url,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "vpf09-independent-viewer",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as error:
        raise GitHubApiError(f"GitHub API вернул HTTP {error.code}") from None
    except (TimeoutError, URLError):
        raise GitHubApiError("GitHub API недоступен") from None
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise GitHubApiError("GitHub API вернул невалидный JSON") from None


class CommentPublisher:
    def __init__(
        self,
        *,
        repository: str,
        pull_request: int,
        request_json: RequestJson = _request_json,
    ) -> None:
        if "/" not in repository:
            raise ValueError("GITHUB_REPOSITORY должен иметь формат owner/repo")
        if pull_request < 1:
            raise ValueError("PR_NUMBER должен быть положительным")
        self._repository = quote(repository, safe="/")
        self._pull_request = pull_request
        self._request_json = request_json

    def publish(self, summary: str) -> int:
        body = f"{COMMENT_MARKER}\n{summary.strip()}"
        if len(body) > MAX_COMMENT_LENGTH:
            body = body[: MAX_COMMENT_LENGTH - 80] + "\n\n… summary обрезан из-за лимита GitHub."
        existing = self._viewer_comments()
        if not existing:
            created = self._request_json(
                "POST",
                self._comments_url(),
                {"body": body},
            )
            return int(created["id"])

        comment_id = int(existing[0]["id"])
        self._request_json(
            "PATCH",
            f"{API_ROOT}/repos/{self._repository}/issues/comments/{comment_id}",
            {"body": body},
        )
        for duplicate in existing[1:]:
            self._request_json(
                "DELETE",
                f"{API_ROOT}/repos/{self._repository}/issues/comments/{duplicate['id']}",
                None,
            )
        return comment_id

    def _viewer_comments(self) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self._request_json(
                "GET",
                f"{self._comments_url()}?per_page=100&page={page}",
                None,
            )
            if not isinstance(payload, list):
                raise GitHubApiError("GitHub API вернул список комментариев неверного типа")
            comments.extend(payload)
            if len(payload) < 100:
                break
            page += 1

        result = []
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            user = comment.get("user")
            login = user.get("login") if isinstance(user, dict) else None
            body = comment.get("body")
            if login == "github-actions[bot]" and isinstance(body, str):
                if COMMENT_MARKER in body:
                    result.append(comment)
        return result

    def _comments_url(self) -> str:
        return (
            f"{API_ROOT}/repos/{self._repository}/issues/"
            f"{self._pull_request}/comments"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-path", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = args.summary_path.read_text("utf-8")
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        pull_request = int(os.environ.get("PR_NUMBER", "0"))
        comment_id = CommentPublisher(
            repository=repository,
            pull_request=pull_request,
        ).publish(summary)
    except (OSError, ValueError, GitHubApiError) as error:
        print(f"Viewer summary update failed: {error}", file=sys.stderr)
        return 1
    print(f"Viewer summary comment: {comment_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

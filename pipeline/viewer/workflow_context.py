"""Получает PR metadata и diff как данные из GitHub API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pipeline.viewer.review_pr import DEFAULT_MAX_DIFF_BYTES


API_ROOT = "https://api.github.com"
JSON_ACCEPT = "application/vnd.github+json"
DIFF_ACCEPT = "application/vnd.github.v3.diff"
RAW_ACCEPT = "application/vnd.github.raw+json"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_FILE_CONTEXT_CHARS = 120_000
MAX_TOTAL_FILE_CONTEXT_CHARS = 500_000
GitHubGet = Callable[[str, str], Any]


class ContextError(RuntimeError):
    """Не удалось доказательно связать workflow run с PR."""


@dataclass(frozen=True)
class PullRequestContext:
    number: int
    title: str
    body: str
    base_sha: str
    head_sha: str
    diff: str
    changed_files: tuple[str, ...]
    file_snapshots: dict[str, str]


def _request_json_or_text(path: str, accept: str) -> Any:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise ContextError("GITHUB_TOKEN не задан")
    request = Request(
        f"{API_ROOT}{path}",
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "vpf09-viewer-context",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as error:
        raise ContextError(f"GitHub API вернул HTTP {error.code}") from None
    except (TimeoutError, URLError):
        raise ContextError("GitHub API недоступен") from None
    except UnicodeError:
        raise ContextError("GitHub API вернул текст в неизвестной кодировке") from None
    if accept == DIFF_ACCEPT:
        return body
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise ContextError("GitHub API вернул невалидный JSON") from None


def _participant_repository(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    repository = value.get("repo")
    if not isinstance(repository, dict):
        return None
    full_name = repository.get("full_name")
    return full_name if isinstance(full_name, str) else None


def _matches_repository(pr: Any, repository: str, head_sha: str) -> bool:
    if not isinstance(pr, dict):
        return False
    head = pr.get("head")
    base = pr.get("base")
    if not isinstance(head, dict) or not isinstance(base, dict):
        return False
    return (
        head.get("sha") == head_sha
        and _participant_repository(head) == repository
        and _participant_repository(base) == repository
        and pr.get("state") in {None, "open"}
    )


def resolve_pull_request(
    *,
    repository: str,
    head_sha: str,
    github_get: GitHubGet,
) -> int:
    if "/" not in repository:
        raise ContextError("repository должен иметь формат owner/repo")
    if not FULL_SHA.fullmatch(head_sha):
        raise ContextError("head_sha должен быть полным 40-символьным SHA")
    payload = github_get(
        f"/repos/{repository}/commits/{head_sha}/pulls",
        JSON_ACCEPT,
    )
    if not isinstance(payload, list):
        raise ContextError("GitHub API вернул список PR неверного типа")
    for pr in payload:
        if _matches_repository(pr, repository, head_sha):
            number = pr.get("number")
            if isinstance(number, int) and number > 0:
                return number
    raise ContextError("не найден same-repository PR для проверяемого SHA")


def _load_pull_request_details(
    *,
    repository: str,
    number: int,
    head_sha: str,
    github_get: GitHubGet,
) -> dict[str, Any]:
    payload = github_get(f"/repos/{repository}/pulls/{number}", JSON_ACCEPT)
    if not _matches_repository(payload, repository, head_sha):
        raise ContextError("PR изменился или не относится к same repository")
    if not isinstance(payload, dict):
        raise ContextError("GitHub API вернул PR неверного типа")
    return payload


def _changed_files(
    *, repository: str, number: int, github_get: GitHubGet
) -> tuple[str, ...]:
    files: list[str] = []
    page = 1
    while True:
        payload = github_get(
            f"/repos/{repository}/pulls/{number}/files?per_page=100&page={page}",
            JSON_ACCEPT,
        )
        if not isinstance(payload, list):
            raise ContextError("GitHub API вернул список файлов PR неверного типа")
        for item in payload:
            if not isinstance(item, dict):
                continue
            filename = item.get("filename")
            if isinstance(filename, str) and filename:
                files.append(filename)
        if len(payload) < 100:
            break
        page += 1
    if not files:
        raise ContextError("PR не содержит изменённых файлов")
    return tuple(dict.fromkeys(files))


def _file_snapshots(
    *,
    repository: str,
    head_sha: str,
    changed_files: tuple[str, ...],
    github_get: GitHubGet,
) -> dict[str, str]:
    snapshots: dict[str, str] = {}
    total_chars = 0
    for path in changed_files:
        encoded_path = quote(path, safe="/")
        try:
            content = github_get(
                f"/repos/{repository}/contents/{encoded_path}?ref={head_sha}",
                RAW_ACCEPT,
            )
        except ContextError:
            continue
        if not isinstance(content, str) or "\x00" in content:
            continue
        if len(content) > MAX_FILE_CONTEXT_CHARS:
            content = content[:MAX_FILE_CONTEXT_CHARS] + "\n[file context truncated]\n"
        if total_chars + len(content) > MAX_TOTAL_FILE_CONTEXT_CHARS:
            break
        snapshots[path] = content
        total_chars += len(content)
    return snapshots


def prepare_context(
    *,
    repository: str,
    head_sha: str,
    output_dir: Path,
    max_diff_bytes: int = DEFAULT_MAX_DIFF_BYTES,
    github_get: GitHubGet | None = None,
) -> PullRequestContext:
    get = github_get or _request_json_or_text
    number = resolve_pull_request(
        repository=repository,
        head_sha=head_sha,
        github_get=get,
    )
    initial = _load_pull_request_details(
        repository=repository,
        number=number,
        head_sha=head_sha,
        github_get=get,
    )
    base = initial.get("base")
    base_sha = base.get("sha") if isinstance(base, dict) else None
    if not isinstance(base_sha, str) or not FULL_SHA.fullmatch(base_sha):
        raise ContextError("PR base SHA имеет неверный формат")

    diff = get(f"/repos/{repository}/pulls/{number}", DIFF_ACCEPT)
    if not isinstance(diff, str):
        raise ContextError("GitHub API вернул diff неверного типа")
    diff_bytes = len(diff.encode("utf-8"))
    if diff_bytes > max_diff_bytes:
        raise ContextError(
            f"diff {diff_bytes} bytes превышает лимит {max_diff_bytes} bytes; "
            "разделите PR на меньшие изменения"
        )

    changed_files = _changed_files(
        repository=repository,
        number=number,
        github_get=get,
    )
    file_snapshots = _file_snapshots(
        repository=repository,
        head_sha=head_sha,
        changed_files=changed_files,
        github_get=get,
    )
    final = _load_pull_request_details(
        repository=repository,
        number=number,
        head_sha=head_sha,
        github_get=get,
    )
    final_base = final.get("base")
    final_base_sha = final_base.get("sha") if isinstance(final_base, dict) else None
    if final_base_sha != base_sha:
        raise ContextError("base SHA изменился во время получения diff")

    title = final.get("title")
    body = final.get("body") or ""
    if not isinstance(title, str) or not title.strip():
        raise ContextError("PR title пуст или имеет неверный тип")
    if not isinstance(body, str):
        raise ContextError("PR body имеет неверный тип")
    return PullRequestContext(
        number=number,
        title=title.strip(),
        body=body.strip(),
        base_sha=base_sha,
        head_sha=head_sha,
        diff=diff,
        changed_files=changed_files,
        file_snapshots=file_snapshots,
    )


def write_context(context: PullRequestContext, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "pr-event.json").write_text(
        json.dumps(
            {
                "pull_request": {
                    "title": context.title,
                    "body": context.body,
                    "base": {"sha": context.base_sha},
                    "head": {"sha": context.head_sha},
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "diff.patch").write_text(context.diff, encoding="utf-8")
    (output_dir / "changed-files.json").write_text(
        json.dumps(context.changed_files, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "file-context.json").write_text(
        json.dumps(context.file_snapshots, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--max-diff-bytes", type=int, default=DEFAULT_MAX_DIFF_BYTES)
    args = parser.parse_args(argv)
    try:
        context = prepare_context(
            repository=args.repository,
            head_sha=args.head_sha,
            output_dir=args.output_dir,
            max_diff_bytes=args.max_diff_bytes,
        )
        write_context(context, args.output_dir)
    except (ContextError, OSError) as error:
        print(f"Viewer context failed: {error}", file=sys.stderr)
        return 1
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"pr_number={context.number}\n")
            output.write(f"base_sha={context.base_sha}\n")
            output.write(f"head_sha={context.head_sha}\n")
    print(f"Viewer context resolved: PR #{context.number}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

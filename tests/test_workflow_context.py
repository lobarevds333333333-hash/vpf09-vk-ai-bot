"""Тесты trusted workflow и загрузки PR data из GitHub API."""

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.viewer.workflow_context import (
    DIFF_ACCEPT,
    JSON_ACCEPT,
    RAW_ACCEPT,
    ContextError,
    prepare_context,
    resolve_pull_request,
    write_context,
)


REPOSITORY = "owner/repo"
BASE_SHA = "592ad79c38e35832be4bf7f71c07a946807d4c85"
HEAD_SHA = "774a34d5b62e7a4833bb28e6712b456faebf92b9"


def pull_request_payload(*, head_sha: str = HEAD_SHA, fork: bool = False) -> dict:
    head_repository = "someone/fork" if fork else REPOSITORY
    return {
        "number": 5,
        "title": "feat: trusted viewer",
        "body": "Проверить безопасный запуск.",
        "base": {"sha": BASE_SHA, "repo": {"full_name": REPOSITORY}},
        "head": {"sha": head_sha, "repo": {"full_name": head_repository}},
    }


class WorkflowContextTest(unittest.TestCase):
    def test_prepares_event_diff_and_changed_files(self) -> None:
        calls: list[tuple[str, str]] = []

        def github_get(path: str, accept: str) -> object:
            calls.append((path, accept))
            if "/commits/" in path:
                return [pull_request_payload()]
            if accept == RAW_ACCEPT:
                return "value = 1\n"
            if path.endswith("/files?per_page=100&page=1"):
                return [{"filename": "pipeline/viewer/review_pr.py"}]
            if accept == DIFF_ACCEPT:
                return "diff --git a/a.py b/a.py\n+value = 1\n"
            return pull_request_payload()

        with tempfile.TemporaryDirectory() as temp_dir:
            context = prepare_context(
                repository=REPOSITORY,
                head_sha=HEAD_SHA,
                output_dir=Path(temp_dir),
                github_get=github_get,
            )
            write_context(context, Path(temp_dir))
            event = json.loads((Path(temp_dir) / "pr-event.json").read_text("utf-8"))
            files = json.loads(
                (Path(temp_dir) / "changed-files.json").read_text("utf-8")
            )
            file_context = json.loads(
                (Path(temp_dir) / "file-context.json").read_text("utf-8")
            )

        self.assertEqual(5, context.number)
        self.assertEqual(HEAD_SHA, event["pull_request"]["head"]["sha"])
        self.assertEqual(["pipeline/viewer/review_pr.py"], files)
        self.assertEqual(
            "value = 1\n",
            file_context["pipeline/viewer/review_pr.py"],
        )
        self.assertIn((f"/repos/{REPOSITORY}/pulls/5", DIFF_ACCEPT), calls)
        self.assertIn(JSON_ACCEPT, {accept for _, accept in calls})

    def test_fork_pull_request_is_rejected(self) -> None:
        def github_get(path: str, accept: str) -> object:
            if "/commits/" in path:
                return [pull_request_payload(fork=True)]
            return pull_request_payload(fork=True)

        with self.assertRaisesRegex(ContextError, "same-repository"):
            resolve_pull_request(
                repository=REPOSITORY,
                head_sha=HEAD_SHA,
                github_get=github_get,
            )

    def test_changed_head_while_loading_diff_is_rejected(self) -> None:
        details_calls = 0

        def github_get(path: str, accept: str) -> object:
            nonlocal details_calls
            if "/commits/" in path:
                return [pull_request_payload()]
            if path.endswith("/files?per_page=100&page=1"):
                return [{"filename": "a.py"}]
            if accept == DIFF_ACCEPT:
                return "diff --git a/a.py b/a.py\n+value = 1\n"
            details_calls += 1
            if details_calls == 1:
                return pull_request_payload()
            return pull_request_payload(head_sha="0" * 40)

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ContextError, "PR изменился"):
                prepare_context(
                    repository=REPOSITORY,
                    head_sha=HEAD_SHA,
                    output_dir=Path(temp_dir),
                    github_get=github_get,
                )


if __name__ == "__main__":
    unittest.main()

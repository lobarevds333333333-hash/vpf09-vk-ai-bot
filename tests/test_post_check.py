"""Тесты explicit Check Run для PR head SHA."""

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.viewer.post_check import (
    CHECK_NAME,
    load_check_result,
    publish_check,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "viewer"
HEAD_SHA = "774a34d5b62e7a4833bb28e6712b456faebf92b9"


class PostCheckTest(unittest.TestCase):
    def test_pass_creates_success_check_for_exact_sha(self) -> None:
        verdict = json.loads((FIXTURES / "pass.json").read_text("utf-8"))
        verdict["reviewed_sha"] = HEAD_SHA
        calls: list[tuple[str, str, dict[str, object]]] = []

        def request_json(method: str, url: str, payload: dict[str, object]) -> object:
            calls.append((method, url, payload))
            return {"id": 123}

        with tempfile.TemporaryDirectory() as temp_dir:
            verdict_path = Path(temp_dir) / "verdict.json"
            summary_path = Path(temp_dir) / "summary.md"
            verdict_path.write_text(json.dumps(verdict), encoding="utf-8")
            summary_path.write_text("PASS evidence", encoding="utf-8")
            result, conclusion, summary = load_check_result(
                verdict_path=verdict_path,
                summary_path=summary_path,
                expected_sha=HEAD_SHA,
            )

        check_id = publish_check(
            repository="owner/repo",
            head_sha=HEAD_SHA,
            result=result,
            conclusion=conclusion,
            summary=summary,
            details_url="https://example.invalid/run",
            request_json=request_json,
        )

        self.assertEqual(123, check_id)
        self.assertEqual("POST", calls[0][0])
        self.assertEqual(CHECK_NAME, calls[0][2]["name"])
        self.assertEqual(HEAD_SHA, calls[0][2]["head_sha"])
        self.assertEqual("success", calls[0][2]["conclusion"])

    def test_non_pass_and_missing_artifacts_create_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            verdict_path = Path(temp_dir) / "missing.json"
            summary_path = Path(temp_dir) / "missing.md"
            result, conclusion, _ = load_check_result(
                verdict_path=verdict_path,
                summary_path=summary_path,
                expected_sha=HEAD_SHA,
            )

        self.assertEqual("FAIL", result)
        self.assertEqual("failure", conclusion)


if __name__ == "__main__":
    unittest.main()

"""Unit-тесты fail-closed независимого CI-viewer."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from pipeline.viewer.apihost_client import (
    APIHOST_RESPONSES_URL,
    ApiHostClient,
    ApiHostError,
)
from pipeline.viewer.contract import validate_verdict
from pipeline.viewer.review_pr import (
    ChangedCode,
    GitRepository,
    ReviewInputError,
    run_review,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "viewer"
BASE_SHA = "7f59ff5717daec2621082f4ff0c1aeb8ecbf72db"
HEAD_SHA = "592ad79c38e35832be4bf7f71c07a946807d4c85"


class FakeRepository:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    def read_changes(self, **_: object) -> ChangedCode:
        if self.error:
            raise self.error
        return ChangedCode(
            base_sha=BASE_SHA,
            reviewed_sha=HEAD_SHA,
            diff="diff --git a/example.py b/example.py\n+value = 1\n",
            changed_files=("example.py",),
        )


class FakeClient:
    def __init__(self, *, output: str = "", error: Exception | None = None) -> None:
        self.output = output
        self.error = error
        self.calls = 0

    def review(self, **_: object) -> str:
        self.calls += 1
        if self.error:
            raise self.error
        return self.output


class ApiHostClientTest(unittest.TestCase):
    def test_request_uses_required_model_effort_and_secret_header(self) -> None:
        response = io.BytesIO(
            json.dumps(
                {
                    "output": [
                        {
                            "content": [
                                {"type": "output_text", "text": '{"verdict":"PASS"}'}
                            ]
                        }
                    ]
                }
            ).encode("utf-8")
        )
        response.__enter__ = lambda self: self  # type: ignore[attr-defined]
        response.__exit__ = lambda *args: False  # type: ignore[attr-defined]

        with patch("pipeline.viewer.apihost_client.urlopen", return_value=response) as call:
            output = ApiHostClient(api_key="test-secret").review(
                instructions="instructions",
                prompt="prompt",
                timeout_seconds=15,
            )

        self.assertEqual('{"verdict":"PASS"}', output)
        request = call.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(APIHOST_RESPONSES_URL, request.full_url)
        self.assertEqual("claude-opus-5.5", payload["model"])
        self.assertEqual({"effort": "high"}, payload["reasoning"])
        self.assertEqual("Bearer test-secret", request.get_header("Authorization"))
        self.assertEqual(15, call.call_args.kwargs["timeout"])

    def test_http_error_does_not_include_api_key(self) -> None:
        error = HTTPError(APIHOST_RESPONSES_URL, 500, "error", {}, None)
        with patch("pipeline.viewer.apihost_client.urlopen", side_effect=error):
            with self.assertRaises(ApiHostError) as raised:
                ApiHostClient(api_key="super-secret").review(
                    instructions="instructions",
                    prompt="prompt",
                )

        self.assertNotIn("super-secret", str(raised.exception))


class ReviewRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.artifact_dir = Path(self.temp_dir.name) / "artifacts"

    def run_with(self, client: FakeClient, *, repository: object | None = None) -> int:
        return run_review(
            workspace=ROOT,
            event_path=FIXTURES / "pr-event.json",
            expected_sha=HEAD_SHA,
            base_sha=BASE_SHA,
            tests_status="Ubuntu: success\nWindows: success",
            artifact_dir=self.artifact_dir,
            max_diff_bytes=100_000,
            timeout_seconds=30,
            dry_run=False,
            client=client,
            repository=repository or FakeRepository(),
        )

    def load_artifact(self) -> dict[str, object]:
        return json.loads(
            (self.artifact_dir / "viewer-verdict.json").read_text("utf-8")
        )

    def test_pass_returns_zero_and_saves_valid_artifact(self) -> None:
        pass_output = (FIXTURES / "pass.json").read_text("utf-8")

        code = self.run_with(FakeClient(output=pass_output))

        self.assertEqual(0, code)
        artifact = self.load_artifact()
        self.assertEqual("PASS", artifact["verdict"])
        self.assertEqual(HEAD_SHA, artifact["reviewed_sha"])
        validate_verdict(artifact)

    def test_fail_returns_nonzero_and_preserves_findings(self) -> None:
        fail_output = (FIXTURES / "fail.json").read_text("utf-8")

        code = self.run_with(FakeClient(output=fail_output))

        self.assertEqual(1, code)
        artifact = self.load_artifact()
        self.assertEqual("FAIL", artifact["verdict"])
        self.assertEqual("P1", artifact["findings"][0]["severity"])

    def test_pass_with_risks_also_blocks_merge(self) -> None:
        verdict = json.loads((FIXTURES / "fail.json").read_text("utf-8"))
        verdict["verdict"] = "PASS_WITH_RISKS"
        verdict["findings"][0]["severity"] = "P3"

        code = self.run_with(FakeClient(output=json.dumps(verdict)))

        self.assertEqual(1, code)

    def test_sha_mismatch_fails_before_api_call(self) -> None:
        client = FakeClient(output="")

        code = self.run_with(
            client,
            repository=FakeRepository(
                error=ReviewInputError("HEAD не совпадает с ожидаемым SHA")
            ),
        )

        self.assertEqual(2, code)
        self.assertEqual(0, client.calls)
        self.assertEqual("FAIL", self.load_artifact()["verdict"])

    def test_event_sha_mismatch_fails_before_git_and_api(self) -> None:
        event = json.loads((FIXTURES / "pr-event.json").read_text("utf-8"))
        event["pull_request"]["head"]["sha"] = "0" * 40
        event_path = Path(self.temp_dir.name) / "event.json"
        event_path.write_text(json.dumps(event), encoding="utf-8")
        client = FakeClient(output="")

        code = run_review(
            workspace=ROOT,
            event_path=event_path,
            expected_sha=HEAD_SHA,
            base_sha=BASE_SHA,
            tests_status="Ubuntu: success",
            artifact_dir=self.artifact_dir,
            max_diff_bytes=100_000,
            timeout_seconds=30,
            dry_run=False,
            client=client,
            repository=FakeRepository(error=AssertionError("git must not be called")),
        )

        self.assertEqual(2, code)
        self.assertEqual(0, client.calls)

    def test_invalid_expected_sha_writes_non_contract_error_artifact(self) -> None:
        code = run_review(
            workspace=ROOT,
            event_path=FIXTURES / "pr-event.json",
            expected_sha="bad-sha",
            base_sha=BASE_SHA,
            tests_status="Ubuntu: success",
            artifact_dir=self.artifact_dir,
            max_diff_bytes=100_000,
            timeout_seconds=30,
            dry_run=False,
            client=FakeClient(output=""),
            repository=FakeRepository(),
        )

        self.assertEqual(2, code)
        self.assertFalse((self.artifact_dir / "viewer-verdict.json").exists())
        error_artifact = json.loads(
            (self.artifact_dir / "viewer-error.json").read_text("utf-8")
        )
        self.assertEqual("infrastructure_error", error_artifact["status"])

    def test_timeout_fails_closed(self) -> None:
        code = self.run_with(
            FakeClient(error=ApiHostError("ApiHost не ответил до таймаута"))
        )

        self.assertEqual(2, code)
        self.assertEqual("FAIL", self.load_artifact()["verdict"])

    def test_api_error_fails_closed_without_secret_header(self) -> None:
        code = self.run_with(FakeClient(error=ApiHostError("ApiHost вернул HTTP 500")))

        self.assertEqual(2, code)
        artifact_text = (self.artifact_dir / "viewer-verdict.json").read_text("utf-8")
        summary_text = (self.artifact_dir / "viewer-summary.md").read_text("utf-8")
        for text in (artifact_text, summary_text):
            self.assertNotIn("Authorization", text)
            self.assertNotIn("Bearer ", text)

    def test_broken_model_json_fails_closed(self) -> None:
        code = self.run_with(FakeClient(output="not json"))

        self.assertEqual(2, code)
        artifact = self.load_artifact()
        self.assertEqual("FAIL", artifact["verdict"])
        self.assertIn("невалидный JSON", artifact["evidence"][0])

    def test_russian_cli_output_survives_cp1252_stream(self) -> None:
        class Cp1252Stream:
            encoding = "cp1252"

            def __init__(self) -> None:
                self.output = ""

            def write(self, text: str) -> int:
                text.encode(self.encoding)
                self.output += text
                return len(text)

            def flush(self) -> None:
                return None

        stream = Cp1252Stream()
        with patch("sys.stdout", stream):
            code = self.run_with(FakeClient(output="not json"))

        self.assertEqual(2, code)
        self.assertIn("Viewer verdict: FAIL", stream.output)

    def test_oversized_diff_is_rejected_before_api(self) -> None:
        class OversizedRepository(FakeRepository):
            def read_changes(self, **kwargs: object) -> ChangedCode:
                if int(kwargs["max_diff_bytes"]) < 1_000_000:
                    raise ReviewInputError(
                        "diff превышает лимит; разделите PR на меньшие изменения"
                    )
                return super().read_changes(**kwargs)

        client = FakeClient(output="")
        code = self.run_with(client, repository=OversizedRepository())

        self.assertEqual(2, code)
        self.assertEqual(0, client.calls)

    def test_dry_run_builds_prompt_without_network(self) -> None:
        client = FakeClient(error=AssertionError("network must not be called"))

        code = run_review(
            workspace=ROOT,
            event_path=FIXTURES / "pr-event.json",
            expected_sha=HEAD_SHA,
            base_sha=BASE_SHA,
            tests_status="Ubuntu: success\nWindows: success",
            artifact_dir=self.artifact_dir,
            max_diff_bytes=100_000,
            timeout_seconds=30,
            dry_run=True,
            client=client,
            repository=FakeRepository(),
        )

        self.assertEqual(0, code)
        self.assertEqual(0, client.calls)
        prompt = (self.artifact_dir / "viewer-prompt.txt").read_text("utf-8")
        self.assertIn(HEAD_SHA, prompt)
        self.assertIn("Ubuntu: success", prompt)
        self.assertIn("example.py", prompt)

    def test_external_diff_context_does_not_execute_pr_checkout(self) -> None:
        diff_path = Path(self.temp_dir.name) / "diff.patch"
        files_path = Path(self.temp_dir.name) / "changed-files.json"
        diff_path.write_text("diff --git a/a.py b/a.py\n+value = 1\n", encoding="utf-8")
        files_path.write_text('["a.py"]', encoding="utf-8")
        pass_output = (FIXTURES / "pass.json").read_text("utf-8")

        code = run_review(
            workspace=ROOT,
            event_path=FIXTURES / "pr-event.json",
            expected_sha=HEAD_SHA,
            base_sha=BASE_SHA,
            tests_status="trusted workflow: success",
            artifact_dir=self.artifact_dir,
            max_diff_bytes=100_000,
            timeout_seconds=30,
            dry_run=False,
            client=FakeClient(output=pass_output),
            repository=FakeRepository(error=AssertionError("PR checkout must not run")),
            diff_path=diff_path,
            changed_files_path=files_path,
        )

        self.assertEqual(0, code)
        self.assertEqual("PASS", self.load_artifact()["verdict"])


class GitRepositoryTest(unittest.TestCase):
    def test_head_mismatch_is_rejected(self) -> None:
        repository = GitRepository(ROOT)
        wrong_sha = "0" * 40

        with self.assertRaisesRegex(ReviewInputError, "HEAD"):
            repository.read_changes(
                base_sha=BASE_SHA,
                expected_sha=wrong_sha,
                max_diff_bytes=100_000,
            )


if __name__ == "__main__":
    unittest.main()

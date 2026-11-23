"""Тесты канонического контракта независимого вьювера."""

import copy
import json
import unittest
from pathlib import Path

from pipeline.viewer.contract import ContractError, validate_verdict


ROOT = Path(__file__).resolve().parents[1]
VIEWER_DIR = ROOT / "pipeline" / "viewer"
FIXTURES = ROOT / "tests" / "fixtures" / "viewer"


def load_fixture(name: str) -> dict[str, object]:
    with (FIXTURES / name).open(encoding="utf-8") as file:
        return json.load(file)


class ViewerContractTest(unittest.TestCase):
    def test_canonical_files_are_present_and_documented(self) -> None:
        schema = json.loads((VIEWER_DIR / "verdict.schema.json").read_text("utf-8"))
        instructions = (VIEWER_DIR / "instructions.md").read_text("utf-8")

        required = {
            "reviewed_sha",
            "verdict",
            "evidence",
            "findings",
            "limitations",
        }
        self.assertEqual(required, set(schema["required"]))
        self.assertEqual(
            {"PASS", "PASS_WITH_RISKS", "FAIL"},
            set(schema["properties"]["verdict"]["enum"]),
        )
        self.assertIn("полный 40-символьный SHA", instructions)
        self.assertIn("Не редактируй файлы", instructions)
        self.assertIn("русском языке", instructions)

    def test_pass_fixture_is_valid(self) -> None:
        verdict = load_fixture("pass.json")

        self.assertIs(validate_verdict(verdict), verdict)

    def test_fail_fixture_is_valid(self) -> None:
        verdict = load_fixture("fail.json")

        self.assertIs(validate_verdict(verdict), verdict)

    def test_empty_or_short_sha_is_rejected(self) -> None:
        for invalid_sha in ("", "592ad79"):
            with self.subTest(sha=invalid_sha):
                verdict = load_fixture("pass.json")
                verdict["reviewed_sha"] = invalid_sha

                with self.assertRaisesRegex(ContractError, "reviewed_sha"):
                    validate_verdict(verdict)

    def test_required_top_level_field_is_not_optional(self) -> None:
        verdict = load_fixture("pass.json")
        del verdict["limitations"]

        with self.assertRaisesRegex(ContractError, "limitations"):
            validate_verdict(verdict)

    def test_finding_requires_evidence_and_action(self) -> None:
        verdict = load_fixture("fail.json")
        broken = copy.deepcopy(verdict)
        del broken["findings"][0]["evidence"]
        del broken["findings"][0]["action"]

        with self.assertRaises(ContractError) as raised:
            validate_verdict(broken)
        self.assertIn("evidence", str(raised.exception))
        self.assertIn("action", str(raised.exception))

    def test_pass_rejects_blocking_findings(self) -> None:
        verdict = load_fixture("fail.json")
        verdict["verdict"] = "PASS"

        with self.assertRaisesRegex(ContractError, "PASS не может"):
            validate_verdict(verdict)

    def test_pass_with_risks_rejects_non_p3_findings(self) -> None:
        verdict = load_fixture("fail.json")
        verdict["verdict"] = "PASS_WITH_RISKS"

        with self.assertRaisesRegex(ContractError, "только findings P3"):
            validate_verdict(verdict)


if __name__ == "__main__":
    unittest.main()

"""Инварианты безопасного разделения untrusted и trusted workflows."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class ViewerWorkflowTest(unittest.TestCase):
    def test_actions_are_pinned_to_full_commit_sha(self) -> None:
        uses_pattern = re.compile(r"^\s*uses:\s+(\S+)", re.MULTILINE)
        for workflow_name in ("tests.yml", "viewer.yml"):
            workflow = (WORKFLOWS / workflow_name).read_text("utf-8")
            references = uses_pattern.findall(workflow)
            self.assertTrue(references)
            for reference in references:
                if reference.startswith(("./", "docker://")):
                    continue
                with self.subTest(workflow=workflow_name, reference=reference):
                    self.assertIn("@", reference)
                    _, revision = reference.rsplit("@", 1)
                    self.assertRegex(revision, r"^[0-9a-f]{40}$")

    def test_pull_request_tests_never_receive_api_secret(self) -> None:
        tests_workflow = (WORKFLOWS / "tests.yml").read_text("utf-8")

        self.assertNotIn("APIHOST_API_KEY", tests_workflow)
        self.assertNotIn("Independent Viewer", tests_workflow)

    def test_trusted_viewer_runs_after_tests_without_pr_checkout(self) -> None:
        viewer_workflow = (WORKFLOWS / "viewer.yml").read_text("utf-8")

        self.assertIn("workflow_run:", viewer_workflow)
        self.assertIn("workflows:\n      - Tests", viewer_workflow)
        self.assertIn("checks: write", viewer_workflow)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", viewer_workflow)
        self.assertIn("--diff-path", viewer_workflow)
        self.assertIn("--file-context-path", viewer_workflow)
        self.assertIn(
            "independent-viewer-${{ github.event.workflow_run.event }}",
            viewer_workflow,
        )
        self.assertNotIn("ref: ${{ github.event.workflow_run.head_sha }}", viewer_workflow)
        self.assertNotIn("pull_request_target", viewer_workflow)


if __name__ == "__main__":
    unittest.main()

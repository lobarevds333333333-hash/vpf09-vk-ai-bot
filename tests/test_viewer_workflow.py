"""Инварианты безопасного разделения untrusted и trusted workflows."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class ViewerWorkflowTest(unittest.TestCase):
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
        self.assertNotIn("ref: ${{ github.event.workflow_run.head_sha }}", viewer_workflow)
        self.assertNotIn("pull_request_target", viewer_workflow)


if __name__ == "__main__":
    unittest.main()

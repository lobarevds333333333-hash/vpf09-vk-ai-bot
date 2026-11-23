"""Тесты конфигурации branch protection."""

import unittest

from scripts.configure_branch_protection import REQUIRED_CHECKS, build_payload


class BranchProtectionTest(unittest.TestCase):
    def test_payload_requires_all_pipeline_checks(self) -> None:
        payload = build_payload()
        contexts = {
            check["context"] for check in payload["required_status_checks"]["checks"]
        }

        self.assertEqual(set(REQUIRED_CHECKS), contexts)
        self.assertTrue(payload["required_status_checks"]["strict"])

    def test_payload_removes_admin_bypass_and_destructive_branch_actions(self) -> None:
        payload = build_payload()

        self.assertTrue(payload["enforce_admins"])
        self.assertTrue(payload["required_conversation_resolution"])
        self.assertFalse(payload["allow_force_pushes"])
        self.assertFalse(payload["allow_deletions"])
        self.assertEqual(0, payload["required_pull_request_reviews"]["required_approving_review_count"])


if __name__ == "__main__":
    unittest.main()

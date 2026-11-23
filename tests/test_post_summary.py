"""Тесты обновления единственного viewer-комментария в PR."""

import unittest

from pipeline.viewer.post_summary import COMMENT_MARKER, CommentPublisher


class FakeApi:
    def __init__(self, comments: list[dict[str, object]]) -> None:
        self.comments = comments
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def __call__(
        self,
        method: str,
        url: str,
        payload: dict[str, object] | None,
    ) -> object:
        self.calls.append((method, url, payload))
        if method == "GET":
            return self.comments
        if method == "POST":
            return {"id": 101}
        return None


class CommentPublisherTest(unittest.TestCase):
    def test_creates_marked_comment_when_none_exists(self) -> None:
        api = FakeApi([])
        publisher = CommentPublisher(
            repository="owner/repo",
            pull_request=7,
            request_json=api,
        )

        comment_id = publisher.publish("## Viewer\n\nPASS")

        self.assertEqual(101, comment_id)
        self.assertEqual("POST", api.calls[-1][0])
        self.assertIn(COMMENT_MARKER, api.calls[-1][2]["body"])

    def test_updates_existing_bot_comment_without_duplicate(self) -> None:
        api = FakeApi(
            [
                {
                    "id": 42,
                    "user": {"login": "github-actions[bot]"},
                    "body": f"{COMMENT_MARKER}\nold",
                }
            ]
        )
        publisher = CommentPublisher(
            repository="owner/repo",
            pull_request=7,
            request_json=api,
        )

        comment_id = publisher.publish("new summary")

        self.assertEqual(42, comment_id)
        self.assertEqual(2, len(api.calls))
        self.assertEqual("PATCH", api.calls[-1][0])
        self.assertTrue(api.calls[-1][1].endswith("/issues/comments/42"))

    def test_ignores_marker_from_non_bot_user(self) -> None:
        api = FakeApi(
            [
                {
                    "id": 99,
                    "user": {"login": "contributor"},
                    "body": COMMENT_MARKER,
                }
            ]
        )
        publisher = CommentPublisher(
            repository="owner/repo",
            pull_request=7,
            request_json=api,
        )

        publisher.publish("new summary")

        self.assertEqual("POST", api.calls[-1][0])

    def test_removes_duplicate_bot_comments(self) -> None:
        bot = {"login": "github-actions[bot]"}
        api = FakeApi(
            [
                {"id": 1, "user": bot, "body": COMMENT_MARKER},
                {"id": 2, "user": bot, "body": COMMENT_MARKER},
            ]
        )
        publisher = CommentPublisher(
            repository="owner/repo",
            pull_request=7,
            request_json=api,
        )

        publisher.publish("new summary")

        self.assertEqual(["GET", "PATCH", "DELETE"], [call[0] for call in api.calls])
        self.assertTrue(api.calls[-1][1].endswith("/issues/comments/2"))


if __name__ == "__main__":
    unittest.main()

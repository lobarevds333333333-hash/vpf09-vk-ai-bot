"""Тесты loopback proxy и установки Codex-агента."""

import json
import threading
import tomllib
import unittest
from pathlib import Path
from urllib.request import urlopen

from pipeline.viewer.apihost_responses_proxy import (
    build_server,
    sanitize_responses_payload,
)
from pipeline.viewer.install_coder_viewer import (
    render_agent_toml,
    scheduled_task_command,
)


class ResponsesSanitizerTest(unittest.TestCase):
    def test_removes_forbidden_fields_recursively(self) -> None:
        payload = {
            "model": "claude-opus-5.5",
            "client_metadata": {"client": "codex"},
            "namespace": "root",
            "input": [
                {
                    "role": "user",
                    "content": "test",
                    "client_metadata": {"nested": True},
                    "namespace": "nested",
                }
            ],
            "web_search": {"enabled": True},
        }

        sanitized = sanitize_responses_payload(payload)

        self.assertNotIn("client_metadata", sanitized)
        self.assertNotIn("namespace", sanitized)
        self.assertNotIn("web_search", sanitized)
        self.assertEqual("test", sanitized["input"][0]["content"])

    def test_preserves_function_tools_and_removes_web_search_tool(self) -> None:
        payload = {
            "tools": [
                {
                    "type": "function",
                    "name": "read_file",
                    "parameters": {"type": "object"},
                },
                {"type": "web_search"},
                {"type": "web_search_preview"},
            ]
        }

        sanitized = sanitize_responses_payload(payload)

        self.assertEqual(1, len(sanitized["tools"]))
        self.assertEqual("function", sanitized["tools"][0]["type"])
        self.assertEqual("read_file", sanitized["tools"][0]["name"])

    def test_health_endpoint_works_without_upstream_request(self) -> None:
        server = build_server(api_key="test-only", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        with urlopen(f"http://127.0.0.1:{server.server_port}/health", timeout=5) as response:
            payload = json.load(response)

        self.assertEqual({"ok": True}, payload)


class CoderViewerInstallerTest(unittest.TestCase):
    def test_generated_agent_uses_canonical_contract_and_read_only(self) -> None:
        instructions = Path("pipeline/viewer/instructions.md").read_text("utf-8")

        generated = render_agent_toml(instructions)

        self.assertIn('model = "claude-opus-5.5"', generated)
        self.assertIn('model_reasoning_effort = "high"', generated)
        self.assertIn('sandbox_mode = "read-only"', generated)
        self.assertIn("Не редактируй файлы", generated)
        self.assertIn("verdict.schema.json", generated)

    def test_instruction_quotes_and_triple_apostrophes_produce_valid_toml(self) -> None:
        generated = render_agent_toml("Инструкция заканчивается кавычкой ' и ''' внутри.")

        parsed = tomllib.loads(generated)

        self.assertEqual(
            "Инструкция заканчивается кавычкой ' и ''' внутри.",
            parsed["developer_instructions"],
        )

    def test_watchdog_task_is_hidden_and_checks_proxy_each_minute(self) -> None:
        command = scheduled_task_command("create", script_path=Path("pipeline/viewer/start_proxy.ps1"))
        command_text = " ".join(command)

        self.assertIn("MINUTE", command)
        self.assertIn("1", command)
        self.assertIn("-WindowStyle Hidden", command_text)
        self.assertIn("start_proxy.ps1", command_text)

    def test_start_script_is_hidden_and_waits_for_health(self) -> None:
        script = Path("pipeline/viewer/start_proxy.ps1").read_text("utf-8")

        self.assertIn("Start-Process", script)
        self.assertIn("-WindowStyle Hidden", script)
        self.assertIn("/health", script)
        self.assertIn("did not become healthy", script)


if __name__ == "__main__":
    unittest.main()

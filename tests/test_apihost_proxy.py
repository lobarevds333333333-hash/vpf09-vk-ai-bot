"""Тесты loopback proxy и установки Codex-агента."""

import json
import socket
import tempfile
import threading
import tomllib
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request
from urllib.request import urlopen

from pipeline.viewer.apihost_responses_proxy import (
    build_server,
    read_proxy_token_file,
    sanitize_responses_payload,
)
from pipeline.viewer.install_coder_viewer import (
    ensure_viewer_proxy_token,
    render_agent_toml,
    watchdog_command,
)


class ResponsesSanitizerTest(unittest.TestCase):
    def start_proxy(self):
        server = build_server(api_key="test-only", port=0, proxy_token="proxy-only")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def test_removes_known_top_level_fields(self) -> None:
        payload = {
            "model": "claude-opus-5.5",
            "client_metadata": {"client": "codex"},
            "namespace": "root",
            "input": [
                {
                    "role": "user",
                    "content": "test",
                    "client_metadata": {"nested": True},
                    "namespace": "legitimate-nested-value",
                }
            ],
            "web_search": {"enabled": True},
        }

        sanitized = sanitize_responses_payload(payload)

        self.assertNotIn("client_metadata", sanitized)
        self.assertNotIn("namespace", sanitized)
        self.assertNotIn("web_search", sanitized)
        self.assertEqual("test", sanitized["input"][0]["content"])
        self.assertEqual(
            "legitimate-nested-value",
            sanitized["input"][0]["namespace"],
        )

    def test_preserves_function_tools_and_removes_web_search_tool(self) -> None:
        payload = {
            "tools": [
                {
                    "type": "function",
                    "name": "read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {"namespace": {"type": "string"}},
                    },
                },
                {"type": "namespace"},
                {"type": "web_search"},
                {"type": "web_search_preview"},
            ]
        }

        sanitized = sanitize_responses_payload(payload)

        self.assertEqual(1, len(sanitized["tools"]))
        self.assertEqual("function", sanitized["tools"][0]["type"])
        self.assertEqual("read_file", sanitized["tools"][0]["name"])
        self.assertIn("namespace", sanitized["tools"][0]["parameters"]["properties"])

    def test_streaming_request_is_preserved(self) -> None:
        sanitized = sanitize_responses_payload({"stream": True, "input": "test"})

        self.assertIs(True, sanitized["stream"])

    def test_health_endpoint_works_without_upstream_request(self) -> None:
        server = self.start_proxy()

        with urlopen(f"http://127.0.0.1:{server.server_port}/health", timeout=5) as response:
            payload = json.load(response)

        self.assertEqual({"ok": True}, payload)

    def test_responses_endpoint_requires_local_token(self) -> None:
        server = self.start_proxy()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/v1/responses",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=5)

        self.assertEqual(401, raised.exception.code)

    def test_responses_endpoint_rejects_non_json_content_type(self) -> None:
        server = self.start_proxy()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/v1/responses",
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "text/plain",
                "Authorization": "Bearer proxy-only",
            },
        )

        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=5)

        self.assertEqual(415, raised.exception.code)

    def test_incomplete_unauthorized_request_does_not_hang(self) -> None:
        server = self.start_proxy()
        with socket.create_connection(("127.0.0.1", server.server_port), timeout=5) as client:
            client.sendall(
                b"POST /v1/responses HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: 100\r\n\r\n{}"
            )
            client.settimeout(3)
            response = client.recv(1024)

        self.assertIn(b" 401 ", response.split(b"\r\n", 1)[0])


class CoderViewerInstallerTest(unittest.TestCase):
    def test_generated_agent_uses_canonical_contract_and_read_only(self) -> None:
        instructions = Path("pipeline/viewer/instructions.md").read_text("utf-8")

        generated = render_agent_toml(instructions)

        self.assertIn('model = "claude-opus-5.5"', generated)
        self.assertIn('model_reasoning_effort = "high"', generated)
        self.assertIn('sandbox_mode = "read-only"', generated)
        self.assertIn('env_key = "VIEWER_PROXY_TOKEN"', generated)
        self.assertIn("Не редактируй файлы", generated)
        self.assertIn("verdict.schema.json", generated)

    def test_instruction_quotes_and_triple_apostrophes_produce_valid_toml(self) -> None:
        generated = render_agent_toml("Инструкция заканчивается кавычкой ' и ''' внутри.")

        parsed = tomllib.loads(generated)

        self.assertEqual(
            "Инструкция заканчивается кавычкой ' и ''' внутри.",
            parsed["developer_instructions"],
        )

    def test_proxy_token_is_generated_once_and_reused(self) -> None:
        values: dict[str, str] = {}
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        token_path = Path(temp_dir.name) / "viewer-proxy-token"

        first = ensure_viewer_proxy_token(
            read_value=lambda name: values.get(name),
            write_value=lambda name, value: values.__setitem__(name, value),
            token_path=token_path,
        )
        second = ensure_viewer_proxy_token(
            read_value=lambda name: values.get(name),
            write_value=lambda name, value: values.__setitem__(name, value),
            token_path=token_path,
        )

        self.assertEqual(first, second)
        self.assertGreaterEqual(len(first), 32)
        self.assertEqual(first, values["VIEWER_PROXY_TOKEN"])
        self.assertEqual(first, read_proxy_token_file(token_path))

    def test_watchdog_startup_is_hidden_and_uses_loop_script(self) -> None:
        command_text = watchdog_command(script_path=Path("pipeline/viewer/watchdog.ps1"))

        self.assertIn("-WindowStyle Hidden", command_text)
        self.assertIn("watchdog.ps1", command_text)

    def test_start_script_is_hidden_and_waits_for_health(self) -> None:
        script = Path("pipeline/viewer/start_proxy.ps1").read_text("utf-8")

        self.assertIn("Start-Process", script)
        self.assertIn("-WindowStyle Hidden", script)
        self.assertIn("/health", script)
        self.assertIn("VIEWER_PROXY_TOKEN", script)
        self.assertIn("viewer-proxy-token", script)
        self.assertIn('GetEnvironmentVariable("APIHOST_API_KEY", "User")', script)
        self.assertIn("did not become healthy", script)

        watchdog = Path("pipeline/viewer/watchdog.ps1").read_text("utf-8")
        self.assertIn("CodexApiHostProxyWatchdog", watchdog)
        self.assertIn("start_proxy.ps1", watchdog)
        self.assertIn("IntervalSeconds", watchdog)
        self.assertIn("viewer-watchdog.stop", watchdog)


if __name__ == "__main__":
    unittest.main()

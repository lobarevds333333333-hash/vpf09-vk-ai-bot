"""Loopback Responses proxy для интерактивного Codex viewer."""

from __future__ import annotations

import argparse
import hmac
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8791
DEFAULT_UPSTREAM_BASE_URL = "https://api.apihost.one/v1"
MAX_REQUEST_BYTES = 10 * 1024 * 1024
FORBIDDEN_FIELDS = {"client_metadata", "namespace", "web_search"}
REMOVED_TOOL_TYPES = {"web_search", "web_search_preview"}
logger = logging.getLogger(__name__)


def sanitize_responses_payload(value: Any) -> Any:
    """Удаляет известные несовместимые поля верхнего уровня запроса."""
    if not isinstance(value, dict):
        return value
    sanitized = {key: item for key, item in value.items() if key not in FORBIDDEN_FIELDS}
    tools = sanitized.get("tools")
    if isinstance(tools, list):
        sanitized["tools"] = [
            tool
            for tool in tools
            if not (
                isinstance(tool, dict) and tool.get("type") in REMOVED_TOOL_TYPES
            )
        ]
    return sanitized


class UpstreamError(RuntimeError):
    def __init__(self, message: str, *, status: int = 502, body: bytes = b"") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class ApiHostUpstream:
    def __init__(self, api_key: str, base_url: str = DEFAULT_UPSTREAM_BASE_URL) -> None:
        if not api_key:
            raise ValueError("APIHOST_API_KEY не задан")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def request(self, path: str, *, payload: Any | None = None) -> tuple[int, bytes]:
        data = None
        method = "GET"
        if payload is not None:
            method = "POST"
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self._base_url}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "vpf09-codex-viewer-proxy",
            },
        )
        try:
            with urlopen(request, timeout=180) as response:
                return response.status, response.read()
        except HTTPError as error:
            body = error.read()
            raise UpstreamError(
                f"ApiHost вернул HTTP {error.code}",
                status=error.code,
                body=body,
            ) from None
        except URLError:
            raise UpstreamError("ApiHost недоступен") from None


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True

    upstream: ApiHostUpstream
    proxy_token: str | None


def make_handler() -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server: ProxyServer
        server_version = "Vpf09ViewerProxy/1.0"

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send_json(200, {"ok": True})
                return
            if self.path == "/v1/models":
                if not self._local_auth_ok():
                    return
                self._proxy("/models", None)
                return
            self._send_json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/v1/responses":
                self._send_json(404, {"error": "not found"})
                return
            if not self._local_auth_ok():
                return
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
            if content_type.lower() != "application/json":
                self._send_json(415, {"error": "application/json required"})
                return
            content_length = self.headers.get("Content-Length")
            try:
                length = int(content_length or "0")
            except ValueError:
                self._send_json(400, {"error": "invalid content length"})
                return
            if length < 1 or length > MAX_REQUEST_BYTES:
                self._send_json(413, {"error": "request body size rejected"})
                return
            raw_body = self.rfile.read(length)
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError:
                self._send_json(400, {"error": "invalid JSON"})
                return
            if not isinstance(payload, dict):
                self._send_json(400, {"error": "response payload must be an object"})
                return
            self._proxy("/responses", sanitize_responses_payload(payload))

        def _local_auth_ok(self) -> bool:
            expected = self.server.proxy_token
            supplied = self.headers.get("X-Viewer-Proxy-Token", "")
            authorization = self.headers.get("Authorization", "")
            bearer = authorization.removeprefix("Bearer ").strip()
            if expected and (
                hmac.compare_digest(supplied, expected)
                or hmac.compare_digest(bearer, expected)
            ):
                return True
            self._send_json(401, {"error": "viewer proxy token required"})
            return False

        def _proxy(self, path: str, payload: Any | None) -> None:
            try:
                status, body = self.server.upstream.request(path, payload=payload)
            except UpstreamError as error:
                self._send_bytes(
                    error.status,
                    b"{\"error\":\"upstream request failed\"}",
                    content_type="application/json",
                )
                logger.error("upstream request failed with status %s", error.status)
                return
            self._send_bytes(status, body, content_type="application/json")

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            self._send_bytes(
                status,
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                content_type="application/json; charset=utf-8",
            )

        def _send_bytes(self, status: int, body: bytes, *, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            logger.info("%s - %s", self.address_string(), format % args)

    return Handler


def build_server(
    *,
    api_key: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    upstream_base_url: str = DEFAULT_UPSTREAM_BASE_URL,
    proxy_token: str,
) -> ProxyServer:
    server = ProxyServer((host, port), make_handler())
    server.upstream = ApiHostUpstream(api_key, upstream_base_url)
    server.proxy_token = proxy_token
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--upstream-base-url", default=DEFAULT_UPSTREAM_BASE_URL)
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    api_key = os.environ.get("APIHOST_API_KEY", "")
    proxy_token = os.environ.get("VIEWER_PROXY_TOKEN", "")
    if not api_key:
        logger.error("APIHOST_API_KEY не задан; proxy не запущен")
        return 1
    if not proxy_token:
        logger.error("VIEWER_PROXY_TOKEN не задан; proxy не запущен")
        return 1
    try:
        server = build_server(
            api_key=api_key,
            host=args.host,
            port=args.port,
            upstream_base_url=args.upstream_base_url,
            proxy_token=proxy_token,
        )
        logger.info("Viewer proxy listening on http://%s:%s", args.host, args.port)
        server.serve_forever()
    except OSError as error:
        logger.error("Не удалось запустить proxy: %s", type(error).__name__)
        return 1
    finally:
        if "server" in locals():
            server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

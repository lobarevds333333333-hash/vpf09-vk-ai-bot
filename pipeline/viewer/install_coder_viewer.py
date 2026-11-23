"""Генерирует глобальный Codex-агент из канонического viewer contract."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INSTRUCTIONS = Path(__file__).with_name("instructions.md")
DEFAULT_OUTPUT = Path.home() / ".codex" / "agents" / "coder-viewer.toml"
DEFAULT_PROXY_SCRIPT = Path(__file__).with_name("start_proxy.ps1")
TASK_NAME = "CodexApiHostProxyWatchdog"


def render_agent_toml(instructions: str) -> str:
    instructions_literal = json.dumps(instructions.rstrip(), ensure_ascii=False)
    return f'''name = "coder-viewer"
description = "Независимый вьювер работы кодового агента. Проверяет исходную задачу, diff, тесты и наблюдаемый результат; выдаёт доказательный PASS или FAIL и не меняет код."
model = "claude-opus-5.5"
model_provider = "apihost"
model_reasoning_effort = "high"
sandbox_mode = "read-only"
nickname_candidates = ["Claude Viewer", "Independent Viewer", "Coder Reviewer"]

developer_instructions = {instructions_literal}

[model_providers.apihost]
name = "ApiHost via Codex adapter"
base_url = "http://127.0.0.1:8791/v1"
wire_api = "responses"
env_key = "VIEWER_PROXY_TOKEN"
'''


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def _read_user_environment(name: str) -> str | None:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
    except (ImportError, FileNotFoundError, OSError):
        return None
    return value if isinstance(value, str) and value else None


def _write_user_environment(name: str, value: str) -> None:
    import ctypes
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        "Environment",
        access=winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    ctypes.windll.user32.SendMessageTimeoutW(
        0xFFFF,
        0x001A,
        0,
        "Environment",
        0x0002,
        5000,
        ctypes.byref(ctypes.c_ulong()),
    )


def ensure_viewer_proxy_token(
    *,
    read_value: Callable[[str], str | None] = _read_user_environment,
    write_value: Callable[[str, str], None] = _write_user_environment,
) -> str:
    token = os.environ.get("VIEWER_PROXY_TOKEN") or read_value("VIEWER_PROXY_TOKEN")
    if not token:
        token = secrets.token_urlsafe(32)
        write_value("VIEWER_PROXY_TOKEN", token)
    os.environ["VIEWER_PROXY_TOKEN"] = token
    return token


def scheduled_task_command(action: str, *, script_path: Path = DEFAULT_PROXY_SCRIPT) -> list[str]:
    if action in {"status", "delete"}:
        arguments = ["schtasks", "/Query" if action == "status" else "/Delete"]
        arguments.extend(["/TN", TASK_NAME])
        if action == "delete":
            arguments.append("/F")
        return arguments
    if action != "create":
        raise ValueError(f"unknown scheduled task action: {action}")

    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    task_command = (
        f'"{powershell}" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden '
        f'-File "{script_path.resolve()}"'
    )
    return [
        "schtasks",
        "/Create",
        "/TN",
        TASK_NAME,
        "/SC",
        "MINUTE",
        "/MO",
        "1",
        "/TR",
        task_command,
        "/F",
    ]


def run_scheduled_task_command(action: str, *, script_path: Path) -> int:
    command = scheduled_task_command(action, script_path=script_path)
    result = subprocess.run(command, check=False)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instructions", type=Path, default=DEFAULT_INSTRUCTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--proxy-script", type=Path, default=DEFAULT_PROXY_SCRIPT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--install-startup", action="store_true")
    parser.add_argument("--remove-startup", action="store_true")
    parser.add_argument("--startup-status", action="store_true")
    args = parser.parse_args(argv)

    try:
        generated = render_agent_toml(args.instructions.read_text("utf-8"))
    except (OSError, ValueError) as error:
        print(f"Не удалось сформировать coder-viewer: {error}", file=sys.stderr)
        return 1
    if args.check:
        try:
            current = args.output.read_text("utf-8")
        except OSError:
            print(f"Файл отсутствует: {args.output}")
            return 1
        if current != generated:
            print(f"coder-viewer устарел: {args.output}")
            return 1
        print(f"coder-viewer актуален: {args.output}")
        return 0

    try:
        ensure_viewer_proxy_token()
        write_atomic(args.output, generated)
    except OSError as error:
        print(f"Не удалось записать coder-viewer: {error}", file=sys.stderr)
        return 1
    print(f"coder-viewer записан: {args.output}")

    if args.install_startup:
        return run_scheduled_task_command("create", script_path=args.proxy_script)
    if args.remove_startup:
        return run_scheduled_task_command("delete", script_path=args.proxy_script)
    if args.startup_status:
        return run_scheduled_task_command("status", script_path=args.proxy_script)
    return 0


if __name__ == "__main__":
    sys.exit(main())

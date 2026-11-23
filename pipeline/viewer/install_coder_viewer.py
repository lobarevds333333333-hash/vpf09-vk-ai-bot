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
DEFAULT_WATCHDOG_SCRIPT = Path(__file__).with_name("watchdog.ps1")
DEFAULT_TOKEN_PATH = Path.home() / ".codex" / "viewer-proxy-token"
TASK_NAME = "CodexApiHostProxyWatchdog"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


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
    token_path: Path = DEFAULT_TOKEN_PATH,
) -> str:
    file_token = None
    try:
        file_token = token_path.read_text("utf-8").strip()
    except OSError:
        pass
    registry_token = read_value("VIEWER_PROXY_TOKEN")
    token = (
        os.environ.get("VIEWER_PROXY_TOKEN")
        or registry_token
        or file_token
    )
    if not token:
        token = secrets.token_urlsafe(32)
    if registry_token != token:
        write_value("VIEWER_PROXY_TOKEN", token)
    if file_token != token:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(token_path, token + "\n")
        try:
            token_path.chmod(0o600)
        except OSError:
            pass
    os.environ["VIEWER_PROXY_TOKEN"] = token
    return token


def watchdog_command(*, script_path: Path = DEFAULT_WATCHDOG_SCRIPT) -> str:
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return (
        f'"{powershell}" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden '
        f'-File "{script_path.resolve()}"'
    )


def install_watchdog(*, script_path: Path = DEFAULT_WATCHDOG_SCRIPT) -> None:
    import winreg

    subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        check=False,
    )
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(
            key,
            TASK_NAME,
            0,
            winreg.REG_SZ,
            watchdog_command(script_path=script_path),
        )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path.resolve()),
        ],
        cwd=str(script_path.resolve().parents[2]),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
        close_fds=True,
    )


def remove_watchdog() -> None:
    import winreg

    subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        check=False,
    )
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            access=winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, TASK_NAME)
    except FileNotFoundError:
        pass


def watchdog_status() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, TASK_NAME)
    except FileNotFoundError:
        return False
    return isinstance(value, str) and bool(value.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instructions", type=Path, default=DEFAULT_INSTRUCTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--proxy-script", type=Path, default=DEFAULT_PROXY_SCRIPT)
    parser.add_argument("--watchdog-script", type=Path, default=DEFAULT_WATCHDOG_SCRIPT)
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
        try:
            install_watchdog(script_path=args.watchdog_script)
        except OSError as error:
            print(f"Не удалось установить watchdog: {error}", file=sys.stderr)
            return 1
        print("watchdog установлен")
        return 0
    if args.remove_startup:
        remove_watchdog()
        print("watchdog удалён из автозапуска")
        return 0
    if args.startup_status:
        installed = watchdog_status()
        print(f"watchdog={'installed' if installed else 'missing'}")
        return 0 if installed else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

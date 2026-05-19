from __future__ import annotations

import shutil
import subprocess


SERVICE_URLS = {
    "chatgpt": "https://chatgpt.com/",
    "claude": "https://claude.ai/new",
    "gemini": "https://gemini.google.com/app",
}


class ClipboardError(RuntimeError):
    pass


class BrowserOpenError(RuntimeError):
    pass


def copy_to_clipboard(text: str) -> str:
    commands = [
        (
            "powershell.exe Set-Clipboard",
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "[Console]::InputEncoding = [System.Text.Encoding]::UTF8; Set-Clipboard -Value ([Console]::In.ReadToEnd())",
            ],
        ),
        ("clip.exe", ["clip.exe"]),
        ("wl-copy", ["wl-copy"]),
        ("xclip", ["xclip", "-selection", "clipboard"]),
        ("xsel", ["xsel", "--clipboard", "--input"]),
        ("pbcopy", ["pbcopy"]),
    ]
    for label, command in commands:
        if _command_exists(command[0]) and _run_input(command, text):
            return label
    raise ClipboardError("No supported clipboard writer found. Install wl-copy, xclip, or use WSL clipboard tools.")


def read_clipboard() -> str:
    commands = [
        (
            "powershell.exe Get-Clipboard",
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-Clipboard -Raw",
            ],
        ),
        ("wl-paste", ["wl-paste"]),
        ("xclip", ["xclip", "-selection", "clipboard", "-o"]),
        ("xsel", ["xsel", "--clipboard", "--output"]),
        ("pbpaste", ["pbpaste"]),
    ]
    for label, command in commands:
        if not _command_exists(command[0]):
            continue
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=10)
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
            continue
        if result.returncode == 0:
            return result.stdout
    raise ClipboardError("No supported clipboard reader found. Install wl-paste, xclip, or use PowerShell in WSL.")


def open_translation_service(service: str) -> str:
    try:
        url = SERVICE_URLS[service]
    except KeyError as exc:
        supported = ", ".join(sorted(SERVICE_URLS))
        raise ValueError(f"Unknown service '{service}'. Supported services: {supported}") from exc
    open_url(url)
    return url


def open_url(url: str) -> None:
    commands = [
        ["cmd.exe", "/c", "start", "", url],
        ["wslview", url],
        ["xdg-open", url],
        ["powershell.exe", "-NoProfile", "-Command", f"Start-Process '{url}'"],
        ["open", url],
    ]
    for command in commands:
        if not _command_exists(command[0]):
            continue
        try:
            result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return
    raise BrowserOpenError(f"Could not open browser automatically. Open this URL manually: {url}")


def _command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def _run_input(command: list[str], text: str) -> bool:
    try:
        result = subprocess.run(command, input=text, capture_output=True, text=True, encoding="utf-8", timeout=10)
    except (OSError, subprocess.SubprocessError, UnicodeEncodeError):
        return False
    return result.returncode == 0

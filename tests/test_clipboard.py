from openlongpdf import clipboard


def test_copy_prefers_powershell_before_clip_exe(monkeypatch):
    attempted = []

    monkeypatch.setattr(clipboard, "_command_exists", lambda command: command in {"powershell.exe", "clip.exe"})

    def fake_run_input(command, text):
        attempted.append(command[0])
        return True

    monkeypatch.setattr(clipboard, "_run_input", fake_run_input)

    method = clipboard.copy_to_clipboard("こんにちは Привет")

    assert method == "powershell.exe Set-Clipboard"
    assert attempted == ["powershell.exe"]


def test_copy_uses_pbcopy_when_only_pbcopy_exists(monkeypatch):
    attempted = []

    monkeypatch.setattr(clipboard, "_command_exists", lambda command: command == "pbcopy")

    def fake_run_input(command, text):
        attempted.append((command, text))
        return True

    monkeypatch.setattr(clipboard, "_run_input", fake_run_input)

    method = clipboard.copy_to_clipboard("こんにちは Привет")

    assert method == "pbcopy"
    assert attempted == [(["pbcopy"], "こんにちは Привет")]


def test_read_clipboard_uses_pbpaste_when_only_pbpaste_exists(monkeypatch):
    attempted = []

    monkeypatch.setattr(clipboard, "_command_exists", lambda command: command == "pbpaste")

    def fake_run(command, **kwargs):
        attempted.append((command, kwargs))
        return clipboard.subprocess.CompletedProcess(command, 0, stdout="from mac clipboard")

    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

    text = clipboard.read_clipboard()

    assert text == "from mac clipboard"
    assert attempted == [
        (
            ["pbpaste"],
            {"capture_output": True, "text": True, "encoding": "utf-8", "timeout": 10},
        )
    ]


def test_open_url_uses_open_when_only_open_exists(monkeypatch):
    attempted = []

    monkeypatch.setattr(clipboard, "_command_exists", lambda command: command == "open")

    def fake_run(command, **kwargs):
        attempted.append((command, kwargs))
        return clipboard.subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

    clipboard.open_url("https://example.test/")

    assert attempted == [
        (
            ["open", "https://example.test/"],
            {"stdout": clipboard.subprocess.DEVNULL, "stderr": clipboard.subprocess.DEVNULL, "timeout": 10},
        )
    ]

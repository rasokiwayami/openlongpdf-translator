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

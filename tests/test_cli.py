from pathlib import Path

import pytest

from openlongpdf.chunking import PageText
from openlongpdf.cli import main
from openlongpdf.project import create_project_from_pages, get_status


def make_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "book_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="eins"), PageText(number=2, text="zwei")],
        pages_per_chunk=1,
    )
    return project_dir


def test_next_copy_open_copies_prompt_and_opens_selected_service(tmp_path, monkeypatch, capsys):
    project_dir = make_project(tmp_path)
    copied = {}
    opened = {}

    monkeypatch.setattr("openlongpdf.cli.copy_to_clipboard", lambda text: copied.setdefault("text", text))
    monkeypatch.setattr("openlongpdf.cli.open_translation_service", lambda service: opened.setdefault("service", service))

    exit_code = main(["next", str(project_dir), "--copy", "--open", "chatgpt"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "prompts/chunk_001_prompt.md" in output.replace("\\", "/")
    assert "translated_chunks/chunk_001_translated.md" in output.replace("\\", "/")
    assert "eins" in copied["text"]
    assert opened["service"] == "chatgpt"


def test_next_print_writes_prompt_to_stdout(tmp_path, capsys):
    project_dir = make_project(tmp_path)

    exit_code = main(["next", str(project_dir), "--print"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Translate the following PDF excerpt" in output
    assert "## Page 1" in output


def test_paste_reads_clipboard_and_saves_next_missing_chunk(tmp_path, monkeypatch, capsys):
    project_dir = make_project(tmp_path)
    monkeypatch.setattr("openlongpdf.cli.read_clipboard", lambda: "translated from clipboard")

    exit_code = main(["paste", str(project_dir)])

    assert exit_code == 0
    assert "Saved translated_chunks/chunk_001_translated.md" in capsys.readouterr().out.replace("\\", "/")
    assert (project_dir / "translated_chunks" / "chunk_001_translated.md").read_text(encoding="utf-8") == (
        "translated from clipboard\n"
    )
    assert get_status(project_dir).next_missing == "chunk_002_translated.md"


def test_paste_reports_empty_clipboard_without_writing(tmp_path, monkeypatch, capsys):
    project_dir = make_project(tmp_path)
    monkeypatch.setattr("openlongpdf.cli.read_clipboard", lambda: "   \n")

    exit_code = main(["paste", str(project_dir)])

    assert exit_code == 2
    assert "Clipboard is empty" in capsys.readouterr().err
    assert not (project_dir / "translated_chunks" / "chunk_001_translated.md").exists()


def test_queue_prints_all_remaining_prompt_targets(tmp_path, capsys):
    project_dir = make_project(tmp_path)

    exit_code = main(["queue", str(project_dir)])

    output = capsys.readouterr().out.replace("\\", "/")
    assert exit_code == 0
    assert "2 chunks remaining" in output
    assert "prompts/chunk_001_prompt.md" in output
    assert "translated_chunks/chunk_001_translated.md" in output
    assert "prompts/chunk_002_prompt.md" in output


def test_queue_write_creates_markdown_checklist(tmp_path, capsys):
    project_dir = make_project(tmp_path)

    exit_code = main(["queue", str(project_dir), "--write"])

    output = capsys.readouterr().out
    queue_path = project_dir / "output" / "translation_queue.md"
    assert exit_code == 0
    assert str(queue_path) in output
    assert "chunk_001" in queue_path.read_text(encoding="utf-8")


def test_pack_writes_multi_chunk_prompt_files(tmp_path, capsys):
    project_dir = make_project(tmp_path)

    exit_code = main(["pack", str(project_dir), "--chunks-per-pack", "2"])

    output = capsys.readouterr().out.replace("\\", "/")
    pack_path = project_dir / "output" / "packs" / "pack_001.md"
    assert exit_code == 0
    assert "Wrote 1 pack" in output
    assert "output/translation_packs.md" in output
    assert pack_path.exists()
    assert "--- BEGIN SOURCE CHUNK chunk_001 ---" in pack_path.read_text(encoding="utf-8")


def test_import_reads_response_file_and_saves_chunks(tmp_path, capsys):
    project_dir = make_project(tmp_path)
    response_path = tmp_path / "response.md"
    response_path.write_text(
        """--- BEGIN TRANSLATED CHUNK chunk_001 ---
translated one
--- END TRANSLATED CHUNK chunk_001 ---

--- BEGIN TRANSLATED CHUNK chunk_002 ---
translated two
--- END TRANSLATED CHUNK chunk_002 ---
""",
        encoding="utf-8",
    )

    exit_code = main(["import", str(project_dir), str(response_path)])

    output = capsys.readouterr().out.replace("\\", "/")
    assert exit_code == 0
    assert "Imported 2 translated chunks" in output
    assert "translated_chunks/chunk_001_translated.md" in output
    assert get_status(project_dir).remaining_chunks == 0

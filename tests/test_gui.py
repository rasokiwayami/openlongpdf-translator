from openlongpdf.chunking import PageText
from openlongpdf.gui import (
    import_response_text,
    mark_assist_pack_sent,
    next_assist_pack,
    render_browser_assist,
    render_dashboard,
    resolve_pack_path,
)
from openlongpdf.project import create_project_from_pages, get_status, write_translation_packs


def make_project(tmp_path):
    project_dir = tmp_path / "book_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="one"), PageText(number=2, text="two")],
        pages_per_chunk=1,
        target_language="Japanese",
    )
    return project_dir


def test_dashboard_shows_pack_workflow_and_status(tmp_path):
    project_dir = make_project(tmp_path)
    write_translation_packs(project_dir, chunks_per_pack=2)

    html = render_dashboard(project_dir)

    assert "OpenLongPDF" in html
    assert "2 chunks total" in html
    assert "pack_001" in html
    assert "Recommended:" in html
    assert "Browser Assist" in html
    assert "/assist" in html
    assert "Copy Pack" in html
    assert "Paste translated response" in html
    assert "Assemble Reading Notes" in html


def test_resolve_pack_path_rejects_path_traversal(tmp_path):
    project_dir = make_project(tmp_path)
    write_translation_packs(project_dir, chunks_per_pack=2)

    try:
        resolve_pack_path(project_dir, "../status.json")
    except ValueError as exc:
        assert "Invalid pack name" in str(exc)
    else:
        raise AssertionError("path traversal should be rejected")


def test_import_response_text_saves_marked_translation(tmp_path):
    project_dir = make_project(tmp_path)
    response = """--- BEGIN TRANSLATED CHUNK chunk_001 ---
## Page 1

translated one
--- END TRANSLATED CHUNK chunk_001 ---
"""

    saved = import_response_text(project_dir, response)

    assert [path.name for path in saved] == ["chunk_001_translated.md"]
    assert get_status(project_dir).remaining_chunks == 1


def test_browser_assist_page_provides_chatgpt_side_helper(tmp_path):
    project_dir = make_project(tmp_path)
    write_translation_packs(project_dir, chunks_per_pack=2)

    html = render_browser_assist(project_dir, base_url="http://127.0.0.1:8765", token="test-token")

    assert "Browser Assist" in html
    assert "Send next OpenLongPDF pack" in html
    assert "Auto-send remaining packs" in html
    assert "javascript:" in html
    assert "test-token" in html
    assert "https://chatgpt.com/" in html
    assert "does not read ChatGPT responses" in html


def test_assist_pack_queue_tracks_sent_packs(tmp_path):
    project_dir = tmp_path / "book_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="one"), PageText(number=2, text="two"), PageText(number=3, text="three")],
        pages_per_chunk=1,
        target_language="Japanese",
    )
    write_translation_packs(project_dir, chunks_per_pack=2)

    first = next_assist_pack(project_dir)
    assert first is not None
    assert first.name == "pack_001"
    assert "Translation Pack 001" in first.text

    mark_assist_pack_sent(project_dir, "pack_001")

    second = next_assist_pack(project_dir)
    assert second is not None
    assert second.name == "pack_002"

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from openlongpdf.chunking import PageText
from openlongpdf.gui import (
    get_assist_summary,
    import_assist_pack_response,
    import_response_text,
    mark_assist_pack_sent,
    next_assist_pack,
    render_browser_assist,
    render_dashboard,
    resolve_pack_path,
    retry_failed_assist_pack,
    reset_assist_state,
    _make_handler,
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
    assert "Start ChatGPT Translation" in html
    assert "Browser Assist" in html
    assert "/assist" in html
    assert "<details" in html


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

    assert "OpenLongPDF Assist" in html
    assert "Chrome extension installed? Click this button once." in html
    assert "Start Translation In ChatGPT" in html
    assert "openlongpdf_server=http%3A%2F%2F127.0.0.1%3A8765" in html
    assert "javascript:" in html
    assert "test-token" in html
    assert "Load unpacked" in html
    assert "OpenLongPDF Bookmarklet" in html
    assert "Advanced" in html


def test_chrome_extension_files_define_chatgpt_assist():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "extension" / "manifest.json").read_text(encoding="utf-8"))
    content = (root / "extension" / "content.js").read_text(encoding="utf-8")
    core = (root / "extension" / "assist-core.js").read_text(encoding="utf-8")

    assert manifest["manifest_version"] == 3
    assert "https://chatgpt.com/*" in manifest["content_scripts"][0]["matches"]
    assert "http://127.0.0.1/*" in manifest["host_permissions"]
    assert "openlongpdf_server" in content
    assert "openlongpdf_token" in content
    assert "openLongPDFStartAssist" in core
    assert "Auto translate all" in core
    assert "/assist/import-response" in core
    assert "waitForSendButton" in core
    assert "hasCompleteTranslatedBlocks" in core
    assert "--- END TRANSLATED CHUNK ---" in core
    assert "送信" in core


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


def test_assist_state_tracks_pack_transitions_and_retry(tmp_path):
    project_dir = make_project(tmp_path)
    write_translation_packs(project_dir, chunks_per_pack=1)

    summary = get_assist_summary(project_dir)
    assert summary.total == 2
    assert summary.pending == 2
    assert summary.next_pack == "pack_001"

    mark_assist_pack_sent(project_dir, "pack_001")
    summary = get_assist_summary(project_dir)
    assert summary.sent == 1
    assert summary.next_pack == "pack_002"

    response = """--- BEGIN TRANSLATED CHUNK chunk_001 ---
translated one
--- END TRANSLATED CHUNK chunk_001 ---
"""
    result = import_assist_pack_response(project_dir, "pack_001", response)

    summary = get_assist_summary(project_dir)
    assert result.assembled is False
    assert result.imported_chunk_names == ["chunk_001"]
    assert summary.imported == 1
    assert summary.pending == 1

    failed_path = import_assist_pack_response(project_dir, "pack_002", "not marked").response_path
    summary = get_assist_summary(project_dir)
    assert summary.failed == 1
    assert summary.last_error == "No translated chunk blocks found in response"
    assert failed_path.name == "pack_002_failed_response.md"

    retry_failed_assist_pack(project_dir, "pack_002")
    assert get_assist_summary(project_dir).pending == 1

    reset_assist_state(project_dir)
    assert get_assist_summary(project_dir).pending == 1


def test_assist_import_response_assembles_when_all_packs_imported(tmp_path):
    project_dir = make_project(tmp_path)
    write_translation_packs(project_dir, chunks_per_pack=1)
    first = """--- BEGIN TRANSLATED CHUNK chunk_001 ---
translated one
--- END TRANSLATED CHUNK chunk_001 ---
"""
    second = """--- BEGIN TRANSLATED CHUNK chunk_002 ---
translated two
--- END TRANSLATED CHUNK chunk_002 ---
"""

    assert import_assist_pack_response(project_dir, "pack_001", first).assembled is False
    result = import_assist_pack_response(project_dir, "pack_002", second)

    assert result.assembled is True
    assert result.markdown_path is not None
    assert result.html_path is not None
    assert result.markdown_path.exists()
    assert result.html_path.exists()
    assert get_status(project_dir).remaining_chunks == 0
    assert get_assist_summary(project_dir).imported == 2


def test_assist_import_response_requires_all_chunks_in_pack(tmp_path):
    project_dir = make_project(tmp_path)
    write_translation_packs(project_dir, chunks_per_pack=2)
    partial = """--- BEGIN TRANSLATED CHUNK chunk_001 ---
translated one
--- END TRANSLATED CHUNK chunk_001 ---
"""

    result = import_assist_pack_response(project_dir, "pack_001", partial)

    assert result.ok is False
    assert "Missing complete translated chunk blocks: chunk_002" == result.error
    assert get_status(project_dir).remaining_chunks == 2
    summary = get_assist_summary(project_dir)
    assert summary.failed == 1
    assert summary.imported == 0


def test_assist_next_json_returns_next_pack(tmp_path):
    project_dir = make_project(tmp_path)
    write_translation_packs(project_dir, chunks_per_pack=1)

    with run_test_server(project_dir) as base_url:
        data = get_json(f"{base_url}/assist/next.json?token=test-token")

    assert data["done"] is False
    assert data["pack"] == "pack_001"
    assert "Translation Pack 001" in data["text"]
    assert data["state"]["pending"] == 2


def test_assist_import_response_endpoint_imports_and_assembles(tmp_path):
    project_dir = make_project(tmp_path)
    write_translation_packs(project_dir, chunks_per_pack=2)
    response = """--- BEGIN TRANSLATED CHUNK chunk_001 ---
translated one
--- END TRANSLATED CHUNK chunk_001 ---

--- BEGIN TRANSLATED CHUNK chunk_002 ---
translated two
--- END TRANSLATED CHUNK chunk_002 ---
"""

    with run_test_server(project_dir) as base_url:
        data = post_json(
            f"{base_url}/assist/import-response?token=test-token",
            {"pack": "pack_001", "responseText": response},
        )

    assert data["ok"] is True
    assert data["pack"] == "pack_001"
    assert data["importedChunkNames"] == ["chunk_001", "chunk_002"]
    assert data["assembled"] is True
    assert (project_dir / "output" / "reading_note.md").exists()
    assert (project_dir / "output" / "index.html").exists()


def test_assist_import_response_endpoint_persists_parse_failure(tmp_path):
    project_dir = make_project(tmp_path)
    write_translation_packs(project_dir, chunks_per_pack=2)

    with run_test_server(project_dir) as base_url:
        try:
            post_json(
                f"{base_url}/assist/import-response?token=test-token",
                {"pack": "pack_001", "responseText": "plain unmarked response"},
            )
        except urllib.error.HTTPError as exc:
            data = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
        else:
            raise AssertionError("unmarked response should fail")

    failed_path = project_dir / "output" / "pack_responses" / "pack_001_failed_response.md"
    assert data["ok"] is False
    assert data["pack"] == "pack_001"
    assert data["error"] == "No translated chunk blocks found in response"
    assert failed_path.read_text(encoding="utf-8") == "plain unmarked response\n"
    summary = get_assist_summary(project_dir)
    assert summary.failed == 1
    assert summary.next_pack is None


class run_test_server:
    def __init__(self, project_dir):
        self.project_dir = project_dir
        self.server = None
        self.thread = None
        self.base_url = ""

    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self.project_dir, base_url="", assist_token="test-token"))
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self.base_url

    def __exit__(self, exc_type, exc, tb):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def get_json(url):
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))

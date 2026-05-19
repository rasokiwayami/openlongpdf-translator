import json
from pathlib import Path

import pytest

from openlongpdf.chunking import PageText, split_pages
from openlongpdf.prompts import build_prompt
from openlongpdf.project import (
    Project,
    create_project_from_pages,
    format_translation_queue,
    get_status,
    import_pack_response,
    next_missing_chunk,
    save_translation,
    write_translation_packs,
)
from openlongpdf.render import assemble_project


def test_split_pages_preserves_chunk_order_and_page_ranges():
    pages = [
        PageText(number=1, text="uno"),
        PageText(number=2, text="dos"),
        PageText(number=3, text="tres"),
        PageText(number=4, text="cuatro"),
        PageText(number=5, text="cinco"),
    ]

    chunks = split_pages(pages, pages_per_chunk=2)

    assert [chunk.name for chunk in chunks] == ["chunk_001", "chunk_002", "chunk_003"]
    assert [(chunk.page_start, chunk.page_end) for chunk in chunks] == [(1, 2), (3, 4), (5, 5)]
    assert [[page.number for page in chunk.pages] for chunk in chunks] == [[1, 2], [3, 4], [5]]


def test_prompt_generation_includes_service_agnostic_instructions_and_page_markers():
    pages = [PageText(number=7, text="Bonjour"), PageText(number=8, text="Au revoir")]
    chunk = split_pages(pages, pages_per_chunk=2)[0]

    prompt = build_prompt(
        source_pdf="livre.pdf",
        chunk=chunk,
        total_chunks=1,
        target_language="English",
    )

    assert "Translate the following PDF excerpt into English" in prompt
    assert "Chunk: 1 of 1" in prompt
    assert "Pages: 7-8" in prompt
    assert "## Page 7" in prompt
    assert "Bonjour" in prompt
    assert "## Page 8" in prompt
    assert "Au revoir" in prompt


def test_project_status_detects_translated_and_next_missing_chunk(tmp_path):
    project_dir = tmp_path / "book_openlongpdf"
    project = create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="one"), PageText(number=2, text="two"), PageText(number=3, text="three")],
        pages_per_chunk=1,
    )
    (project_dir / "translated_chunks" / "chunk_001_translated.md").write_text("translated one", encoding="utf-8")
    (project_dir / "translated_chunks" / "chunk_003_translated.md").write_text("translated three", encoding="utf-8")

    status = get_status(project_dir)
    next_chunk = next_missing_chunk(project)

    assert status.total_chunks == 3
    assert status.translated_chunks == 2
    assert status.remaining_chunks == 1
    assert status.next_missing == "chunk_002_translated.md"
    assert next_chunk.name == "chunk_002"


def test_save_translation_uses_next_missing_target(tmp_path):
    project_dir = tmp_path / "book_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="one"), PageText(number=2, text="two")],
        pages_per_chunk=1,
    )
    save_translation(project_dir, "translated one", overwrite=False)

    target = project_dir / "translated_chunks" / "chunk_001_translated.md"

    assert target.read_text(encoding="utf-8") == "translated one\n"
    assert get_status(project_dir).next_missing == "chunk_002_translated.md"


def test_save_translation_refuses_to_overwrite_existing_target(tmp_path):
    project_dir = tmp_path / "book_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="one")],
        pages_per_chunk=1,
    )
    target = project_dir / "translated_chunks" / "chunk_001_translated.md"
    target.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError):
        save_translation(project_dir, "replacement", overwrite=False, chunk_name="chunk_001")

    assert target.read_text(encoding="utf-8") == "existing"


def test_assemble_reads_translated_chunks_in_manifest_order(tmp_path):
    project_dir = tmp_path / "book_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="one"), PageText(number=2, text="two")],
        pages_per_chunk=1,
    )
    (project_dir / "translated_chunks" / "chunk_002_translated.md").write_text("second", encoding="utf-8")
    (project_dir / "translated_chunks" / "chunk_001_translated.md").write_text("first", encoding="utf-8")

    outputs = assemble_project(project_dir)
    markdown = outputs.markdown_path.read_text(encoding="utf-8")

    assert markdown.index("first") < markdown.index("second")


def test_assemble_escapes_translated_content_in_html(tmp_path):
    project_dir = tmp_path / "book_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="one")],
        pages_per_chunk=1,
    )
    (project_dir / "translated_chunks" / "chunk_001_translated.md").write_text(
        "A <script>alert('x')</script> & B",
        encoding="utf-8",
    )

    outputs = assemble_project(project_dir)
    html = outputs.html_path.read_text(encoding="utf-8")

    assert "<script>" not in html
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt; &amp; B" in html
    assert 'id="top"' in html


def test_project_status_json_is_updated_after_save(tmp_path):
    project_dir = tmp_path / "book_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="one")],
        pages_per_chunk=1,
    )

    save_translation(project_dir, "translated", overwrite=False)

    status_json = json.loads((project_dir / "status.json").read_text(encoding="utf-8"))
    assert status_json["translated_chunks"] == 1
    assert status_json["remaining_chunks"] == 0
    assert status_json["next_missing"] is None


def test_translation_queue_lists_remaining_prompt_and_target_paths(tmp_path):
    project_dir = tmp_path / "book_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[
            PageText(number=1, text="one"),
            PageText(number=2, text="two"),
            PageText(number=3, text="three"),
        ],
        pages_per_chunk=1,
    )
    save_translation(project_dir, "translated one", overwrite=False)

    queue = format_translation_queue(project_dir)

    assert "2 chunks remaining" in queue
    assert "chunk_001" not in queue
    assert "- [ ] chunk_002 (Pages 2)" in queue
    assert "`prompts/chunk_002_prompt.md`" in queue
    assert "`translated_chunks/chunk_002_translated.md`" in queue
    assert "- [ ] chunk_003 (Pages 3)" in queue


def test_translation_queue_can_include_translated_chunks(tmp_path):
    project_dir = tmp_path / "book_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="one"), PageText(number=2, text="two")],
        pages_per_chunk=1,
    )
    save_translation(project_dir, "translated one", overwrite=False)

    queue = format_translation_queue(project_dir, include_translated=True)

    assert "2 chunks total" in queue
    assert "- [x] chunk_001 (Pages 1)" in queue
    assert "- [ ] chunk_002 (Pages 2)" in queue


def test_translation_packs_group_remaining_chunks_and_write_index(tmp_path):
    project_dir = tmp_path / "book_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[
            PageText(number=1, text="one"),
            PageText(number=2, text="two"),
            PageText(number=3, text="three"),
            PageText(number=4, text="four"),
            PageText(number=5, text="five"),
        ],
        pages_per_chunk=1,
        target_language="Japanese",
    )
    save_translation(project_dir, "translated one", overwrite=False)

    result = write_translation_packs(project_dir, chunks_per_pack=2)

    assert [path.name for path in result.pack_paths] == ["pack_001.md", "pack_002.md"]
    index_text = result.index_path.read_text(encoding="utf-8")
    assert "2 packs generated" in index_text
    assert "chunk_002, chunk_003" in index_text
    assert "output/pack_responses/pack_001_response.md" in index_text
    first_pack = result.pack_paths[0].read_text(encoding="utf-8")
    assert "Translate the following PDF excerpts into Japanese" in first_pack
    assert "--- BEGIN TRANSLATED CHUNK chunk_002 ---" in first_pack
    assert "--- END TRANSLATED CHUNK chunk_003 ---" in first_pack
    assert "--- BEGIN SOURCE CHUNK chunk_002 ---" in first_pack
    assert "## Page 2" in first_pack
    assert "--- BEGIN SOURCE CHUNK chunk_004 ---" not in first_pack


def test_translation_pack_index_quotes_import_paths_with_spaces(tmp_path):
    project_dir = tmp_path / "book with spaces_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book with spaces.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="one")],
        pages_per_chunk=1,
    )

    result = write_translation_packs(project_dir, chunks_per_pack=1)

    index_text = result.index_path.read_text(encoding="utf-8")
    assert "openlongpdf import '" in index_text
    assert "' '" in index_text


def test_import_pack_response_saves_marked_chunks_and_updates_status(tmp_path):
    project_dir = tmp_path / "book_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="one"), PageText(number=2, text="two")],
        pages_per_chunk=1,
    )
    response = """--- BEGIN TRANSLATED CHUNK chunk_001 ---
## Page 1

translated one
--- END TRANSLATED CHUNK chunk_001 ---

--- BEGIN TRANSLATED CHUNK chunk_002 ---
## Page 2

translated two
--- END TRANSLATED CHUNK chunk_002 ---
"""

    saved_paths = import_pack_response(project_dir, response)

    assert [path.name for path in saved_paths] == ["chunk_001_translated.md", "chunk_002_translated.md"]
    assert (project_dir / "translated_chunks" / "chunk_001_translated.md").read_text(encoding="utf-8") == (
        "## Page 1\n\ntranslated one\n"
    )
    assert get_status(project_dir).remaining_chunks == 0


def test_import_pack_response_refuses_to_overwrite_existing_chunk(tmp_path):
    project_dir = tmp_path / "book_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="one"), PageText(number=2, text="two")],
        pages_per_chunk=1,
    )
    save_translation(project_dir, "existing", overwrite=False, chunk_name="chunk_001")
    response = """--- BEGIN TRANSLATED CHUNK chunk_001 ---
replacement
--- END TRANSLATED CHUNK chunk_001 ---

--- BEGIN TRANSLATED CHUNK chunk_002 ---
translated two
--- END TRANSLATED CHUNK chunk_002 ---
"""

    with pytest.raises(FileExistsError):
        import_pack_response(project_dir, response)

    assert (project_dir / "translated_chunks" / "chunk_001_translated.md").read_text(encoding="utf-8") == "existing\n"
    assert not (project_dir / "translated_chunks" / "chunk_002_translated.md").exists()


def test_project_can_load_non_ascii_paths(tmp_path):
    project_dir = tmp_path / "本_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "資料.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="こんにちは")],
        pages_per_chunk=1,
    )

    project = Project.load(project_dir)

    assert project.source_pdf.endswith("資料.pdf")
    assert project.chunks[0].page_start == 1

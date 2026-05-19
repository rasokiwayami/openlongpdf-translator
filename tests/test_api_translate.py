import pytest

from openlongpdf.api_translate import (
    ApiTranslationClient,
    ApiTranslationConfig,
    translate_project,
)
from openlongpdf.chunking import PageText
from openlongpdf.project import create_project_from_pages, get_status, save_translation


class FakeClient(ApiTranslationClient):
    def __init__(self):
        self.prompts = []

    def translate(self, prompt: str, *, config: ApiTranslationConfig) -> str:
        self.prompts.append((prompt, config))
        return f"translated call {len(self.prompts)}"


def test_translate_project_requires_confirmation_before_calling_api(tmp_path):
    project_dir = tmp_path / "book_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="one")],
        pages_per_chunk=1,
        target_language="Japanese",
    )
    client = FakeClient()
    config = ApiTranslationConfig(model="paid-model", api_key="secret")

    with pytest.raises(RuntimeError, match="Re-run with --yes"):
        translate_project(project_dir, client=client, config=config, yes=False)

    assert client.prompts == []
    assert get_status(project_dir).remaining_chunks == 1


def test_translate_project_sends_missing_chunks_and_saves_each_result(tmp_path):
    project_dir = tmp_path / "book_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="one"), PageText(number=2, text="two")],
        pages_per_chunk=1,
        target_language="Japanese",
    )
    client = FakeClient()
    config = ApiTranslationConfig(model="paid-model", api_key="secret")

    result = translate_project(project_dir, client=client, config=config, yes=True)

    assert result.planned.total_chunks == 2
    assert result.planned.chunks_to_translate == 2
    assert result.planned.prompt_chars > 0
    assert [path.name for path in result.saved_paths] == ["chunk_001_translated.md", "chunk_002_translated.md"]
    assert (project_dir / "translated_chunks" / "chunk_001_translated.md").read_text(encoding="utf-8") == (
        "translated call 1\n"
    )
    assert len(client.prompts) == 2
    assert "Translate the following PDF excerpt into Japanese" in client.prompts[0][0]
    assert get_status(project_dir).remaining_chunks == 0


def test_translate_project_resumes_by_skipping_existing_translations(tmp_path):
    project_dir = tmp_path / "book_openlongpdf"
    create_project_from_pages(
        pdf_path=tmp_path / "book.pdf",
        project_dir=project_dir,
        pages=[PageText(number=1, text="one"), PageText(number=2, text="two")],
        pages_per_chunk=1,
    )
    save_translation(project_dir, "already done", chunk_name="chunk_001")
    client = FakeClient()
    config = ApiTranslationConfig(model="paid-model", api_key="secret")

    result = translate_project(project_dir, client=client, config=config, yes=True)

    assert result.planned.chunks_to_translate == 1
    assert [path.name for path in result.saved_paths] == ["chunk_002_translated.md"]
    assert len(client.prompts) == 1

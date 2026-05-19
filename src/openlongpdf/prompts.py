from __future__ import annotations

from .chunking import Chunk, format_page_range, render_source_chunk


def build_prompt(
    *,
    source_pdf: str,
    chunk: Chunk,
    total_chunks: int,
    target_language: str = "English",
) -> str:
    source_text = render_source_chunk(chunk)
    page_range = format_page_range(chunk.page_start, chunk.page_end)
    return (
        f"Translate the following PDF excerpt into {target_language} as page-aware reading notes.\n\n"
        "Requirements:\n"
        "- Preserve page headings such as `## Page 7` so the notes remain page-aware.\n"
        "- Keep the chunk order and do not merge this chunk with other chunks.\n"
        "- Do not invent text for missing or unclear source text.\n"
        "- Return only the translated reading notes for this chunk.\n\n"
        f"Source PDF: {source_pdf}\n"
        f"Chunk: {chunk.index} of {total_chunks}\n"
        f"Pages: {page_range}\n\n"
        "--- BEGIN PAGE-AWARE SOURCE ---\n"
        f"{source_text}"
        "--- END PAGE-AWARE SOURCE ---\n"
    )

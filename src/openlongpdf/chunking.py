from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class PageText:
    number: int
    text: str


@dataclass(frozen=True)
class Chunk:
    index: int
    name: str
    page_start: int
    page_end: int
    pages: list[PageText]

    @property
    def source_filename(self) -> str:
        return f"{self.name}.md"

    @property
    def prompt_filename(self) -> str:
        return f"{self.name}_prompt.md"

    @property
    def translated_filename(self) -> str:
        return f"{self.name}_translated.md"


def split_pages(pages: Sequence[PageText], pages_per_chunk: int = 10) -> list[Chunk]:
    if pages_per_chunk < 1:
        raise ValueError("pages_per_chunk must be at least 1")

    chunks: list[Chunk] = []
    ordered_pages = list(pages)
    for offset in range(0, len(ordered_pages), pages_per_chunk):
        chunk_pages = ordered_pages[offset : offset + pages_per_chunk]
        index = len(chunks) + 1
        chunks.append(
            Chunk(
                index=index,
                name=f"chunk_{index:03d}",
                page_start=chunk_pages[0].number,
                page_end=chunk_pages[-1].number,
                pages=chunk_pages,
            )
        )
    return chunks


def render_source_chunk(chunk: Chunk) -> str:
    lines = [
        f"# {chunk.name}",
        "",
        f"Pages: {format_page_range(chunk.page_start, chunk.page_end)}",
        "",
    ]
    for page in chunk.pages:
        text = page.text.strip()
        lines.extend([f"## Page {page.number}", "", text if text else "[No extractable text on this page]", ""])
    return "\n".join(lines).rstrip() + "\n"


def format_page_range(page_start: int, page_end: int) -> str:
    if page_start == page_end:
        return str(page_start)
    return f"{page_start}-{page_end}"

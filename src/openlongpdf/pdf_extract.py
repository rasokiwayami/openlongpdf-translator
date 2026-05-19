from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from .chunking import PageText


def extract_pdf_pages(pdf_path: str | Path) -> list[PageText]:
    path = Path(pdf_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    if not path.is_file():
        raise ValueError(f"PDF path is not a file: {path}")

    reader = PdfReader(str(path))
    pages: list[PageText] = []
    for index, page in enumerate(reader.pages, start=1):
        pages.append(PageText(number=index, text=page.extract_text() or ""))
    return pages

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path

from .chunking import format_page_range
from .project import Project


@dataclass(frozen=True)
class AssembleOutputs:
    markdown_path: Path
    html_path: Path


def assemble_project(project_dir: str | Path) -> AssembleOutputs:
    project = Project.load(project_dir)
    output_dir = project.project_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "reading_note.md"
    html_path = output_dir / "index.html"

    chunk_texts = [(chunk, _read_translation(project, chunk)) for chunk in project.chunks]
    markdown_path.write_text(_render_markdown(project, chunk_texts), encoding="utf-8")
    html_path.write_text(_render_html(project, chunk_texts), encoding="utf-8")
    return AssembleOutputs(markdown_path=markdown_path, html_path=html_path)


def _read_translation(project: Project, chunk) -> str:
    path = project.abs_path(chunk.translated_path)
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return f"[Missing translation for {chunk.name}]"
    return path.read_text(encoding="utf-8").rstrip()


def _render_markdown(project: Project, chunk_texts) -> str:
    lines = [
        "# Reading Notes",
        "",
        f"Source PDF: `{project.source_pdf}`",
        f"Total pages: {project.total_pages}",
        f"Total chunks: {len(project.chunks)}",
        "",
        "## Table of Contents",
        "",
    ]
    for chunk, _text in chunk_texts:
        page_range = format_page_range(chunk.page_start, chunk.page_end)
        lines.append(f"- [Chunk {chunk.index:03d} (Pages {page_range})](#chunk-{chunk.index:03d})")
    lines.append("")

    for chunk, text in chunk_texts:
        page_range = format_page_range(chunk.page_start, chunk.page_end)
        lines.extend(
            [
                f'<a id="chunk-{chunk.index:03d}"></a>',
                f"## Chunk {chunk.index:03d} (Pages {page_range})",
                "",
                text,
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_html(project: Project, chunk_texts) -> str:
    title = "Reading Notes"
    toc = "\n".join(
        f'<li><a href="#chunk-{chunk.index:03d}">Chunk {chunk.index:03d} '
        f"(Pages {html.escape(format_page_range(chunk.page_start, chunk.page_end))})</a></li>"
        for chunk, _text in chunk_texts
    )
    sections = "\n".join(_render_chunk_section(chunk, text, len(chunk_texts)) for chunk, text in chunk_texts)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light dark; }}
    body {{
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.65;
      background: #f7f7f4;
      color: #1f2933;
    }}
    main {{
      max-width: 880px;
      margin: 0 auto;
      padding: 32px 20px 56px;
      background: #ffffff;
      min-height: 100vh;
    }}
    h1, h2, h3 {{ line-height: 1.25; }}
    a {{ color: #075985; }}
    .meta {{ color: #5f6c7b; }}
    nav ul {{ columns: 2; padding-left: 1.2rem; }}
    section {{ border-top: 1px solid #d8dee5; padding-top: 24px; margin-top: 32px; }}
    .chunk-nav {{ display: flex; gap: 16px; flex-wrap: wrap; margin-top: 24px; }}
    pre, code {{ white-space: pre-wrap; }}
    @media (max-width: 680px) {{
      main {{ padding: 24px 16px 40px; }}
      nav ul {{ columns: 1; }}
    }}
  </style>
</head>
<body>
<main>
  <h1 id="top">Reading Notes</h1>
  <p class="meta">Source PDF: {html.escape(project.source_pdf)}</p>
  <p class="meta">Total pages: {project.total_pages} · Total chunks: {len(project.chunks)}</p>
  <nav aria-label="Table of contents">
    <h2>Table of Contents</h2>
    <ul>
{toc}
    </ul>
  </nav>
{sections}
</main>
</body>
</html>
"""


def _render_chunk_section(chunk, text: str, total_chunks: int) -> str:
    page_range = html.escape(format_page_range(chunk.page_start, chunk.page_end))
    previous_link = (
        f'<a href="#chunk-{chunk.index - 1:03d}">Previous chunk</a>' if chunk.index > 1 else ""
    )
    next_link = (
        f'<a href="#chunk-{chunk.index + 1:03d}">Next chunk</a>' if chunk.index < total_chunks else ""
    )
    nav = "\n      ".join(link for link in (previous_link, next_link, '<a href="#top">Top</a>') if link)
    return f"""  <section id="chunk-{chunk.index:03d}">
    <h2>Chunk {chunk.index:03d} <span class="meta">(Pages {page_range})</span></h2>
{_markdownish_to_html(text)}
    <div class="chunk-nav">
      {nav}
    </div>
  </section>"""


def _markdownish_to_html(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            escaped = "<br>\n".join(html.escape(line) for line in paragraph)
            output.append(f"    <p>{escaped}</p>")
            paragraph.clear()

    for line in lines:
        if not line.strip():
            flush_paragraph()
            continue
        if line.startswith("### "):
            flush_paragraph()
            output.append(f"    <h4>{html.escape(line[4:].strip())}</h4>")
        elif line.startswith("## "):
            flush_paragraph()
            output.append(f"    <h3>{html.escape(line[3:].strip())}</h3>")
        elif line.startswith("# "):
            flush_paragraph()
            output.append(f"    <h3>{html.escape(line[2:].strip())}</h3>")
        else:
            paragraph.append(line)
    flush_paragraph()
    return "\n".join(output) if output else "    <p></p>"

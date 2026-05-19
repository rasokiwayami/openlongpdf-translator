from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .chunking import PageText, format_page_range, render_source_chunk, split_pages
from .prompts import build_prompt


STATUS_FILE = "status.json"


@dataclass(frozen=True)
class ProjectChunk:
    index: int
    name: str
    page_start: int
    page_end: int
    source_path: str
    prompt_path: str
    translated_path: str

    @property
    def translated_filename(self) -> str:
        return Path(self.translated_path).name


@dataclass(frozen=True)
class ProjectStatus:
    total_chunks: int
    translated_chunks: int
    remaining_chunks: int
    next_missing: str | None


@dataclass(frozen=True)
class PackWriteResult:
    index_path: Path
    pack_paths: list[Path]


@dataclass(frozen=True)
class Project:
    project_dir: Path
    source_pdf: str
    pages_per_chunk: int
    total_pages: int
    target_language: str
    created_at: str
    chunks: list[ProjectChunk]

    @classmethod
    def load(cls, project_dir: str | Path) -> "Project":
        root = Path(project_dir).expanduser()
        data = _read_status_data(root)
        return cls(
            project_dir=root,
            source_pdf=data["source_pdf"],
            pages_per_chunk=int(data["pages_per_chunk"]),
            total_pages=int(data["total_pages"]),
            target_language=data.get("target_language", "English"),
            created_at=data.get("created_at", ""),
            chunks=[
                ProjectChunk(
                    index=int(item["index"]),
                    name=item["name"],
                    page_start=int(item["page_start"]),
                    page_end=int(item["page_end"]),
                    source_path=item["source_path"],
                    prompt_path=item["prompt_path"],
                    translated_path=item["translated_path"],
                )
                for item in data["chunks"]
            ],
        )

    def abs_path(self, relative_path: str) -> Path:
        return self.project_dir / relative_path


def default_project_dir(pdf_path: str | Path) -> Path:
    path = Path(pdf_path).expanduser()
    return path.with_name(f"{path.stem}_openlongpdf")


def create_project_from_pages(
    *,
    pdf_path: str | Path,
    project_dir: str | Path | None = None,
    pages: list[PageText],
    pages_per_chunk: int = 10,
    target_language: str = "English",
) -> Project:
    if pages_per_chunk < 1:
        raise ValueError("pages_per_chunk must be at least 1")

    source_pdf = str(Path(pdf_path).expanduser())
    root = Path(project_dir).expanduser() if project_dir else default_project_dir(pdf_path)
    source_dir = root / "source_chunks"
    prompt_dir = root / "prompts"
    translated_dir = root / "translated_chunks"
    output_dir = root / "output"
    for directory in (source_dir, prompt_dir, translated_dir, output_dir):
        directory.mkdir(parents=True, exist_ok=True)

    chunks = split_pages(pages, pages_per_chunk=pages_per_chunk)
    project_chunks: list[ProjectChunk] = []
    for chunk in chunks:
        source_rel = f"source_chunks/{chunk.source_filename}"
        prompt_rel = f"prompts/{chunk.prompt_filename}"
        translated_rel = f"translated_chunks/{chunk.translated_filename}"
        (root / source_rel).write_text(render_source_chunk(chunk), encoding="utf-8")
        (root / prompt_rel).write_text(
            build_prompt(
                source_pdf=Path(source_pdf).name,
                chunk=chunk,
                total_chunks=len(chunks),
                target_language=target_language,
            ),
            encoding="utf-8",
        )
        project_chunks.append(
            ProjectChunk(
                index=chunk.index,
                name=chunk.name,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                source_path=source_rel,
                prompt_path=prompt_rel,
                translated_path=translated_rel,
            )
        )

    now = _utc_now()
    project = Project(
        project_dir=root,
        source_pdf=source_pdf,
        pages_per_chunk=pages_per_chunk,
        total_pages=len(pages),
        target_language=target_language,
        created_at=now,
        chunks=project_chunks,
    )
    _write_status(project)
    _write_manifest(project)
    return project


def get_status(project_dir: str | Path) -> ProjectStatus:
    project = Project.load(project_dir)
    return _calculate_status(project)


def format_status(status: ProjectStatus) -> str:
    next_text = status.next_missing if status.next_missing is not None else "none"
    return (
        f"{status.total_chunks} chunks total, "
        f"{status.translated_chunks} translated, "
        f"{status.remaining_chunks} remaining, "
        f"next: {next_text}"
    )


def format_translation_queue(project_dir: str | Path, *, include_translated: bool = False) -> str:
    project = Project.load(project_dir)
    status = _calculate_status(project)
    chunks = [chunk for chunk in project.chunks if include_translated or not _has_translation(project, chunk)]
    scope = "total" if include_translated else "remaining"
    lines = [
        "# Translation Queue",
        "",
        f"- Project: `{project.project_dir}`",
        f"- Source PDF: `{project.source_pdf}`",
        f"- Status: {format_status(status)}",
        f"- Showing: {len(chunks)} chunks {scope}",
        "",
    ]
    if not chunks:
        lines.append("No chunks to translate.")
        return "\n".join(lines) + "\n"

    for chunk in chunks:
        checked = "x" if _has_translation(project, chunk) else " "
        page_range = format_page_range(chunk.page_start, chunk.page_end)
        lines.extend(
            [
                f"- [{checked}] {chunk.name} (Pages {page_range})",
                f"  - Prompt: `{chunk.prompt_path}`",
                f"  - Save translated text to: `{chunk.translated_path}`",
            ]
        )
    return "\n".join(lines) + "\n"


def write_translation_queue(project_dir: str | Path, *, include_translated: bool = False) -> Path:
    project = Project.load(project_dir)
    output_dir = project.project_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "translation_queue.md"
    path.write_text(format_translation_queue(project.project_dir, include_translated=include_translated), encoding="utf-8")
    return path


def write_translation_packs(
    project_dir: str | Path,
    *,
    chunks_per_pack: int = 4,
    include_translated: bool = False,
) -> PackWriteResult:
    if chunks_per_pack < 1:
        raise ValueError("chunks_per_pack must be at least 1")

    project = Project.load(project_dir)
    chunks = [chunk for chunk in project.chunks if include_translated or not _has_translation(project, chunk)]
    packs = [chunks[offset : offset + chunks_per_pack] for offset in range(0, len(chunks), chunks_per_pack)]

    output_dir = project.project_dir / "output"
    pack_dir = output_dir / "packs"
    response_dir = output_dir / "pack_responses"
    pack_dir.mkdir(parents=True, exist_ok=True)
    response_dir.mkdir(parents=True, exist_ok=True)

    pack_paths: list[Path] = []
    for index, pack_chunks in enumerate(packs, start=1):
        path = pack_dir / f"pack_{index:03d}.md"
        path.write_text(
            _format_translation_pack(
                project=project,
                pack_index=index,
                total_packs=len(packs),
                chunks=pack_chunks,
            ),
            encoding="utf-8",
        )
        pack_paths.append(path)

    index_path = output_dir / "translation_packs.md"
    index_path.write_text(
        _format_translation_pack_index(project, pack_paths, packs),
        encoding="utf-8",
    )
    return PackWriteResult(index_path=index_path, pack_paths=pack_paths)


def import_pack_response(
    project_dir: str | Path,
    response_text: str,
    *,
    overwrite: bool = False,
) -> list[Path]:
    project = Project.load(project_dir)
    blocks = _parse_pack_response(response_text)
    if not blocks:
        raise ValueError("No translated chunk blocks found in response")

    seen: set[str] = set()
    targets: list[tuple[str, str, Path]] = []
    for chunk_name, text in blocks:
        if chunk_name in seen:
            raise ValueError(f"Duplicate translated chunk block: {chunk_name}")
        seen.add(chunk_name)
        chunk = _find_chunk(project, chunk_name)
        if not text.strip():
            raise ValueError(f"Translated chunk block is empty: {chunk_name}")
        target = project.abs_path(chunk.translated_path)
        if target.exists() and target.read_text(encoding="utf-8").strip() and not overwrite:
            raise FileExistsError(f"Refusing to overwrite existing translated chunk: {target}")
        targets.append((chunk_name, text.strip(), target))

    saved: list[Path] = []
    for chunk_name, text, _target in targets:
        saved.append(save_translation(project.project_dir, text, overwrite=overwrite, chunk_name=chunk_name))
    return saved


def import_pack_response_file(
    project_dir: str | Path,
    response_file: str | Path,
    *,
    overwrite: bool = False,
) -> list[Path]:
    path = Path(response_file).expanduser()
    return import_pack_response(project_dir, path.read_text(encoding="utf-8"), overwrite=overwrite)


def translated_chunk_names_in_response(response_text: str) -> list[str]:
    return [chunk_name for chunk_name, _text in _parse_pack_response(response_text)]


def next_missing_chunk(project_or_dir: Project | str | Path) -> ProjectChunk | None:
    project = project_or_dir if isinstance(project_or_dir, Project) else Project.load(project_or_dir)
    for chunk in project.chunks:
        if not _has_translation(project, chunk):
            return chunk
    return None


def save_translation(
    project_dir: str | Path,
    text: str,
    *,
    overwrite: bool = False,
    chunk_name: str | None = None,
) -> Path:
    project = Project.load(project_dir)
    chunk = _find_chunk(project, chunk_name) if chunk_name else next_missing_chunk(project)
    if chunk is None:
        raise RuntimeError("No missing translated chunks remain")

    target = project.abs_path(chunk.translated_path)
    if target.exists() and target.read_text(encoding="utf-8").strip() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing translated chunk: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text.rstrip() + "\n", encoding="utf-8")
    _write_status(project)
    return target


def _find_chunk(project: Project, chunk_name: str) -> ProjectChunk:
    normalized = chunk_name.removesuffix("_translated.md").removesuffix(".md")
    for chunk in project.chunks:
        if chunk.name == normalized:
            return chunk
    raise ValueError(f"Unknown chunk: {chunk_name}")


def _calculate_status(project: Project) -> ProjectStatus:
    translated = sum(1 for chunk in project.chunks if _has_translation(project, chunk))
    next_chunk = next_missing_chunk(project)
    return ProjectStatus(
        total_chunks=len(project.chunks),
        translated_chunks=translated,
        remaining_chunks=len(project.chunks) - translated,
        next_missing=next_chunk.translated_filename if next_chunk else None,
    )


def _has_translation(project: Project, chunk: ProjectChunk) -> bool:
    path = project.abs_path(chunk.translated_path)
    return path.exists() and bool(path.read_text(encoding="utf-8").strip())


def _format_translation_pack(
    *,
    project: Project,
    pack_index: int,
    total_packs: int,
    chunks: list[ProjectChunk],
) -> str:
    chunk_names = ", ".join(chunk.name for chunk in chunks)
    marker_examples = "\n\n".join(
        [
            f"--- BEGIN TRANSLATED CHUNK {chunk.name} ---\n"
            f"<translated notes for {chunk.name}>\n"
            f"--- END TRANSLATED CHUNK {chunk.name} ---"
            for chunk in chunks
        ]
    )
    source_blocks = "\n\n".join(
        [
            f"--- BEGIN SOURCE CHUNK {chunk.name} ---\n"
            f"{project.abs_path(chunk.source_path).read_text(encoding='utf-8').rstrip()}\n"
            f"--- END SOURCE CHUNK {chunk.name} ---"
            for chunk in chunks
        ]
    )
    return (
        f"# Translation Pack {pack_index:03d}\n\n"
        f"Translate the following PDF excerpts into {project.target_language} as page-aware reading notes.\n\n"
        "Requirements:\n"
        "- Preserve page headings such as `## Page 7` so the notes remain page-aware.\n"
        "- Keep chunk boundaries separate; do not merge chunks together.\n"
        "- Do not invent text for missing or unclear source text.\n"
        "- Return only the translated chunk blocks, using the exact markers below.\n\n"
        f"Source PDF: {Path(project.source_pdf).name}\n"
        f"Pack: {pack_index} of {total_packs}\n"
        f"Chunks in this pack: {chunk_names}\n\n"
        "Required output format:\n\n"
        f"{marker_examples}\n\n"
        "--- BEGIN PACK SOURCE ---\n"
        f"{source_blocks}\n"
        "--- END PACK SOURCE ---\n"
    )


def _format_translation_pack_index(
    project: Project,
    pack_paths: list[Path],
    packs: list[list[ProjectChunk]],
) -> str:
    status = _calculate_status(project)
    lines = [
        "# Translation Packs",
        "",
        f"- Project: `{project.project_dir}`",
        f"- Source PDF: `{project.source_pdf}`",
        f"- Status: {format_status(status)}",
        f"- Packs: {len(pack_paths)} packs generated",
        "",
    ]
    if not pack_paths:
        lines.append("No chunks to pack.")
        return "\n".join(lines) + "\n"

    for path, chunks in zip(pack_paths, packs, strict=True):
        response_path = project.project_dir / "output" / "pack_responses" / f"{path.stem}_response.md"
        chunk_names = ", ".join(chunk.name for chunk in chunks)
        lines.extend(
            [
                f"- [ ] {path.stem}: {chunk_names}",
                f"  - Prompt pack: `{_project_relative(project, path)}`",
                f"  - Copy pack: `openlongpdf copy-pack {_shell_quote(project.project_dir)} {path.stem} --open chatgpt`",
                f"  - Save translated response to: `{_project_relative(project, response_path)}`",
                f"  - Import: `openlongpdf import {_shell_quote(project.project_dir)} {_shell_quote(response_path)}`",
            ]
        )
    return "\n".join(lines) + "\n"


_TRANSLATED_BLOCK_RE = re.compile(
    r"^--- BEGIN TRANSLATED CHUNK (?P<name>chunk_\d{3}) ---[ \t]*\r?\n"
    r"(?P<text>.*?)"
    r"\r?\n--- END TRANSLATED CHUNK(?: (?P=name))?(?: ---)?[ \t]*$",
    re.DOTALL | re.MULTILINE,
)


def _parse_pack_response(response_text: str) -> list[tuple[str, str]]:
    text = _strip_outer_code_fence(response_text)
    return [(match.group("name"), match.group("text")) for match in _TRANSLATED_BLOCK_RE.finditer(text)]


def _strip_outer_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```") or not stripped.endswith("```"):
        return text
    lines = stripped.splitlines()
    if len(lines) < 2 or not lines[0].startswith("```") or lines[-1].strip() != "```":
        return text
    return "\n".join(lines[1:-1]).strip()


def _project_relative(project: Project, path: Path) -> str:
    return path.relative_to(project.project_dir).as_posix()


def _shell_quote(value: str | Path) -> str:
    return shlex.quote(str(value))


def _read_status_data(project_dir: Path) -> dict[str, Any]:
    status_path = project_dir / STATUS_FILE
    if not status_path.exists():
        raise FileNotFoundError(f"Project status file not found: {status_path}")
    return json.loads(status_path.read_text(encoding="utf-8"))


def _write_status(project: Project) -> None:
    status = _calculate_status(project)
    data = {
        "source_pdf": project.source_pdf,
        "pages_per_chunk": project.pages_per_chunk,
        "total_pages": project.total_pages,
        "target_language": project.target_language,
        "created_at": project.created_at,
        "updated_at": _utc_now(),
        "total_chunks": status.total_chunks,
        "translated_chunks": status.translated_chunks,
        "remaining_chunks": status.remaining_chunks,
        "next_missing": status.next_missing,
        "chunks": [
            {
                "index": chunk.index,
                "name": chunk.name,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "source_path": chunk.source_path,
                "prompt_path": chunk.prompt_path,
                "translated_path": chunk.translated_path,
            }
            for chunk in project.chunks
        ],
    }
    project.project_dir.mkdir(parents=True, exist_ok=True)
    (project.project_dir / STATUS_FILE).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_manifest(project: Project) -> None:
    lines = [
        "# OpenLongPDF Manifest",
        "",
        f"- Source PDF: `{project.source_pdf}`",
        f"- Total pages: {project.total_pages}",
        f"- Pages per chunk: {project.pages_per_chunk}",
        f"- Total chunks: {len(project.chunks)}",
        "",
        "| Chunk | Pages | Source | Prompt | Translation target |",
        "| --- | --- | --- | --- | --- |",
    ]
    for chunk in project.chunks:
        lines.append(
            "| "
            f"{chunk.name} | "
            f"{format_page_range(chunk.page_start, chunk.page_end)} | "
            f"`{chunk.source_path}` | "
            f"`{chunk.prompt_path}` | "
            f"`{chunk.translated_path}` |"
        )
    (project.project_dir / "manifest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

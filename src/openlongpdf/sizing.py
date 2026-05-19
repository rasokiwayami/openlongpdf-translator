from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from .project import Project


DEFAULT_MAX_PROMPT_CHARS = 40_000
DEFAULT_MAX_SOURCE_CHARS = 40_000


@dataclass(frozen=True)
class ChunkSize:
    name: str
    page_start: int
    page_end: int
    source_chars: int
    prompt_chars: int


@dataclass(frozen=True)
class PackRecommendation:
    chunks_per_pack: int
    estimated_packs: int
    total_chunks: int
    max_prompt_chars: int
    max_source_chars: int
    largest_prompt_chars: int
    largest_source_chars: int
    average_prompt_chars: int
    average_source_chars: int


def measure_chunk_sizes(project_dir: str | Path, *, include_translated: bool = False) -> list[ChunkSize]:
    project = Project.load(project_dir)
    sizes: list[ChunkSize] = []
    for chunk in project.chunks:
        if not include_translated and _has_translation(project, chunk.translated_path):
            continue
        source_text = project.abs_path(chunk.source_path).read_text(encoding="utf-8")
        prompt_text = project.abs_path(chunk.prompt_path).read_text(encoding="utf-8")
        sizes.append(
            ChunkSize(
                name=chunk.name,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                source_chars=len(source_text),
                prompt_chars=len(prompt_text),
            )
        )
    return sizes


def recommend_chunks_per_pack(
    project_dir: str | Path,
    *,
    include_translated: bool = False,
    max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS,
    max_source_chars: int = DEFAULT_MAX_SOURCE_CHARS,
) -> PackRecommendation:
    if max_prompt_chars < 1:
        raise ValueError("max_prompt_chars must be at least 1")
    if max_source_chars < 1:
        raise ValueError("max_source_chars must be at least 1")

    sizes = measure_chunk_sizes(project_dir, include_translated=include_translated)
    if not sizes:
        return PackRecommendation(
            chunks_per_pack=1,
            estimated_packs=0,
            total_chunks=0,
            max_prompt_chars=max_prompt_chars,
            max_source_chars=max_source_chars,
            largest_prompt_chars=0,
            largest_source_chars=0,
            average_prompt_chars=0,
            average_source_chars=0,
        )

    largest_prompt = max(size.prompt_chars for size in sizes)
    largest_source = max(size.source_chars for size in sizes)
    prompt_limited = max_prompt_chars // max(1, largest_prompt)
    source_limited = max_source_chars // max(1, largest_source)
    chunks_per_pack = max(1, min(len(sizes), prompt_limited, source_limited))
    return PackRecommendation(
        chunks_per_pack=chunks_per_pack,
        estimated_packs=math.ceil(len(sizes) / chunks_per_pack),
        total_chunks=len(sizes),
        max_prompt_chars=max_prompt_chars,
        max_source_chars=max_source_chars,
        largest_prompt_chars=largest_prompt,
        largest_source_chars=largest_source,
        average_prompt_chars=round(sum(size.prompt_chars for size in sizes) / len(sizes)),
        average_source_chars=round(sum(size.source_chars for size in sizes) / len(sizes)),
    )


def format_pack_recommendation(recommendation: PackRecommendation) -> str:
    if recommendation.total_chunks == 0:
        return "\n".join(
            [
                "No untranslated chunks need packing.",
                f"Safety budgets: {recommendation.max_prompt_chars} prompt chars, "
                f"{recommendation.max_source_chars} source chars.",
            ]
        )
    return "\n".join(
        [
            f"Chunks considered: {recommendation.total_chunks}",
            f"Recommended chunks per pack: {recommendation.chunks_per_pack}",
            f"Estimated packs: {recommendation.estimated_packs}",
            f"Largest chunk: {recommendation.largest_prompt_chars} prompt chars, "
            f"{recommendation.largest_source_chars} source chars",
            f"Average chunk: {recommendation.average_prompt_chars} prompt chars, "
            f"{recommendation.average_source_chars} source chars",
            f"Safety budgets: {recommendation.max_prompt_chars} prompt chars, "
            f"{recommendation.max_source_chars} source chars per pack",
        ]
    )


def _has_translation(project: Project, translated_path: str) -> bool:
    path = project.abs_path(translated_path)
    return path.exists() and bool(path.read_text(encoding="utf-8").strip())

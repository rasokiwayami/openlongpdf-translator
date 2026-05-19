from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .project import Project, save_translation


DEFAULT_BASE_URL = "https://api.openai.com/v1"


@dataclass(frozen=True)
class ApiTranslationConfig:
    model: str
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    temperature: float = 0.0
    timeout: float = 120.0
    max_output_tokens: int | None = None
    retries: int = 2


@dataclass(frozen=True)
class TranslationPlan:
    total_chunks: int
    chunks_to_translate: int
    prompt_chars: int


@dataclass(frozen=True)
class TranslationResult:
    planned: TranslationPlan
    saved_paths: list[Path]


class ApiTranslationClient(Protocol):
    def translate(self, prompt: str, *, config: ApiTranslationConfig) -> str:
        ...


class OpenAICompatibleClient:
    def translate(self, prompt: str, *, config: ApiTranslationConfig) -> str:
        request = urllib.request.Request(
            _chat_completions_url(config.base_url),
            data=json.dumps(_request_payload(prompt, config)).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(config.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=config.timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
                return _extract_message_content(data)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                last_error = exc
                if attempt >= config.retries:
                    break
                time.sleep(2**attempt)
        raise RuntimeError(f"API translation request failed: {last_error}")


def translate_project(
    project_dir: str | Path,
    *,
    client: ApiTranslationClient,
    config: ApiTranslationConfig,
    yes: bool = False,
    overwrite: bool = False,
    limit: int | None = None,
) -> TranslationResult:
    project = Project.load(project_dir)
    chunks = [chunk for chunk in project.chunks if overwrite or not _has_translation(project, chunk)]
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        chunks = chunks[:limit]
    prompts = [(chunk, project.abs_path(chunk.prompt_path).read_text(encoding="utf-8")) for chunk in chunks]
    plan = TranslationPlan(
        total_chunks=len(project.chunks),
        chunks_to_translate=len(prompts),
        prompt_chars=sum(len(prompt) for _chunk, prompt in prompts),
    )

    if not yes:
        raise RuntimeError(
            f"{plan.chunks_to_translate} chunks will be translated with model '{config.model}'. Re-run with --yes."
        )

    saved_paths: list[Path] = []
    for chunk, prompt in prompts:
        translated = client.translate(prompt, config=config)
        saved_paths.append(save_translation(project.project_dir, translated, overwrite=overwrite, chunk_name=chunk.name))
    return TranslationResult(planned=plan, saved_paths=saved_paths)


def plan_translation(project_dir: str | Path, *, overwrite: bool = False, limit: int | None = None) -> TranslationPlan:
    project = Project.load(project_dir)
    chunks = [chunk for chunk in project.chunks if overwrite or not _has_translation(project, chunk)]
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        chunks = chunks[:limit]
    prompt_chars = sum(len(project.abs_path(chunk.prompt_path).read_text(encoding="utf-8")) for chunk in chunks)
    return TranslationPlan(total_chunks=len(project.chunks), chunks_to_translate=len(chunks), prompt_chars=prompt_chars)


def _request_payload(prompt: str, config: ApiTranslationConfig) -> dict:
    payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": config.temperature,
    }
    if config.max_output_tokens is not None:
        payload["max_tokens"] = config.max_output_tokens
    return payload


def _chat_completions_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/chat/completions"


def _extract_message_content(data: dict) -> str:
    content = data["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError("API response did not contain translated text")
    return content


def _has_translation(project: Project, chunk) -> bool:
    path = project.abs_path(chunk.translated_path)
    return path.exists() and bool(path.read_text(encoding="utf-8").strip())

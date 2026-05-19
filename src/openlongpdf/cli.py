from __future__ import annotations

import argparse
import os
import shlex
import sys
from pathlib import Path

from .api_translate import ApiTranslationConfig, OpenAICompatibleClient, plan_translation, translate_project
from .clipboard import BrowserOpenError, ClipboardError, copy_to_clipboard, open_translation_service, read_clipboard
from .pdf_extract import extract_pdf_pages
from .project import (
    Project,
    create_project_from_pages,
    format_translation_queue,
    format_status,
    get_status,
    import_pack_response_file,
    next_missing_chunk,
    save_translation,
    write_translation_packs,
    write_translation_queue,
)
from .render import assemble_project


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openlongpdf",
        description="Turn long foreign-language PDFs into page-aware reading notes.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="extract page text and create translation prompts")
    prepare.add_argument("pdf", help="text-layer PDF to prepare")
    prepare.add_argument("--pages-per-chunk", type=int, default=10, help="number of PDF pages per prompt chunk")
    prepare.add_argument("--project-dir", help="output project directory; defaults to <pdf_stem>_openlongpdf")
    prepare.add_argument("--target-language", default="English", help="translation target language for prompts")
    prepare.set_defaults(func=cmd_prepare)

    status = subparsers.add_parser("status", help="show translation progress")
    status.add_argument("project_dir")
    status.set_defaults(func=cmd_status)

    next_cmd = subparsers.add_parser("next", help="show the next prompt and translation target")
    next_cmd.add_argument("project_dir")
    next_cmd.add_argument("--copy", action="store_true", help="copy the next prompt to the clipboard")
    next_cmd.add_argument("--print", action="store_true", dest="print_prompt", help="print the prompt text")
    next_cmd.add_argument("--open", choices=["chatgpt", "claude", "gemini"], help="open a translator website")
    next_cmd.set_defaults(func=cmd_next)

    queue = subparsers.add_parser("queue", help="show all prompt files and translation targets")
    queue.add_argument("project_dir")
    queue.add_argument("--all", action="store_true", help="include chunks that already have translations")
    queue.add_argument("--write", action="store_true", help="write output/translation_queue.md")
    queue.set_defaults(func=cmd_queue)

    pack = subparsers.add_parser("pack", help="write multi-chunk prompt packs for manual translation")
    pack.add_argument("project_dir")
    pack.add_argument("--chunks-per-pack", type=int, default=4, help="number of chunks per prompt pack")
    pack.add_argument("--all", action="store_true", help="include chunks that already have translations")
    pack.set_defaults(func=cmd_pack)

    copy_pack = subparsers.add_parser("copy-pack", help="copy a prompt pack to the clipboard")
    copy_pack.add_argument("project_dir")
    copy_pack.add_argument("pack", help="pack name such as pack_001 or pack_001.md")
    copy_pack.add_argument("--open", choices=["chatgpt", "claude", "gemini"], help="open a translator website")
    copy_pack.set_defaults(func=cmd_copy_pack)

    paste = subparsers.add_parser("paste", help="save clipboard text as the next translated chunk")
    paste.add_argument("project_dir")
    paste.add_argument("--overwrite", action="store_true", help="allow replacing an existing translated chunk")
    paste.add_argument("--chunk", help="advanced: target a specific chunk name such as chunk_003")
    paste.set_defaults(func=cmd_paste)

    import_cmd = subparsers.add_parser("import", help="import a marked multi-chunk translation response")
    import_cmd.add_argument("project_dir")
    import_cmd.add_argument("response_file")
    import_cmd.add_argument("--overwrite", action="store_true", help="allow replacing existing translated chunks")
    import_cmd.set_defaults(func=cmd_import)

    translate = subparsers.add_parser("translate", help="translate missing chunks through a paid OpenAI-compatible API")
    translate.add_argument("project_dir")
    translate.add_argument("--model", required=True, help="model name to send to the provider")
    translate.add_argument("--base-url", default="https://api.openai.com/v1", help="OpenAI-compatible API base URL")
    translate.add_argument("--api-key-env", default="OPENAI_API_KEY", help="environment variable that contains the API key")
    translate.add_argument("--yes", action="store_true", help="actually call the paid API after showing the plan")
    translate.add_argument("--overwrite", action="store_true", help="retranslate chunks that already have translations")
    translate.add_argument("--limit", type=int, help="translate at most this many chunks")
    translate.add_argument("--timeout", type=float, default=120.0, help="HTTP request timeout in seconds")
    translate.add_argument("--retries", type=int, default=2, help="retry count per chunk")
    translate.add_argument("--temperature", type=float, default=0.0, help="sampling temperature")
    translate.add_argument("--max-output-tokens", type=int, help="optional max_tokens value for each request")
    translate.set_defaults(func=cmd_translate)

    assemble = subparsers.add_parser("assemble", help="assemble translated chunks into Markdown and HTML")
    assemble.add_argument("project_dir")
    assemble.set_defaults(func=cmd_assemble)

    return parser


def cmd_prepare(args: argparse.Namespace) -> int:
    pdf_path = Path(args.pdf).expanduser()
    project_dir = Path(args.project_dir).expanduser() if args.project_dir else None
    pages = extract_pdf_pages(pdf_path)
    project = create_project_from_pages(
        pdf_path=pdf_path,
        project_dir=project_dir,
        pages=pages,
        pages_per_chunk=args.pages_per_chunk,
        target_language=args.target_language,
    )
    status = get_status(project.project_dir)
    print(f"Created project: {project.project_dir}")
    print(f"Extracted {project.total_pages} pages into {status.total_chunks} chunks.")
    print(f"Next: openlongpdf next {_shell_quote(project.project_dir)} --copy --open chatgpt")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    print(format_status(get_status(args.project_dir)))
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    project = Project.load(args.project_dir)
    chunk = next_missing_chunk(project)
    if chunk is None:
        print(f"All chunks are translated. Run: openlongpdf assemble {_shell_quote(project.project_dir)}")
        return 0

    prompt_path = project.abs_path(chunk.prompt_path)
    target_path = project.abs_path(chunk.translated_path)
    prompt_text = prompt_path.read_text(encoding="utf-8")
    print(f"Next prompt: {chunk.prompt_path}")
    print(f"Translation target: {chunk.translated_path}")

    if args.copy:
        try:
            method = copy_to_clipboard(prompt_text)
            print(f"Copied prompt to clipboard using {method}.")
        except ClipboardError as exc:
            print(f"Clipboard copy unavailable: {exc}", file=sys.stderr)

    if args.open:
        try:
            url = open_translation_service(args.open)
            print(f"Opened {args.open}: {url}")
        except (BrowserOpenError, ValueError) as exc:
            print(str(exc), file=sys.stderr)

    if args.print_prompt:
        print()
        print(prompt_text, end="" if prompt_text.endswith("\n") else "\n")

    if not prompt_path.exists():
        print(f"Prompt path does not exist: {prompt_path}", file=sys.stderr)
        return 2
    print(f"Save translated text to: {target_path}")
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    if args.write:
        path = write_translation_queue(args.project_dir, include_translated=args.all)
        print(f"Wrote {path}")
        return 0
    print(format_translation_queue(args.project_dir, include_translated=args.all), end="")
    return 0


def cmd_pack(args: argparse.Namespace) -> int:
    result = write_translation_packs(
        args.project_dir,
        chunks_per_pack=args.chunks_per_pack,
        include_translated=args.all,
    )
    suffix = "" if len(result.pack_paths) == 1 else "s"
    print(f"Wrote {len(result.pack_paths)} pack{suffix}.")
    print(f"Wrote {result.index_path}")
    for path in result.pack_paths:
        print(f"- {path}")
    return 0


def cmd_copy_pack(args: argparse.Namespace) -> int:
    project = Project.load(args.project_dir)
    pack_path = _resolve_pack_path(project, args.pack)
    pack_text = pack_path.read_text(encoding="utf-8")
    try:
        method = copy_to_clipboard(pack_text)
    except ClipboardError as exc:
        print(f"Clipboard copy unavailable: {exc}", file=sys.stderr)
        return 2

    relative_pack = pack_path.relative_to(project.project_dir)
    response_path = project.project_dir / "output" / "pack_responses" / f"{pack_path.stem}_response.md"
    print(f"Copied {relative_pack} to clipboard using {method}.")
    print(f"Save translated response to: {response_path.relative_to(project.project_dir)}")

    if args.open:
        try:
            url = open_translation_service(args.open)
            print(f"Opened {args.open}: {url}")
        except (BrowserOpenError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
    return 0


def cmd_paste(args: argparse.Namespace) -> int:
    try:
        text = read_clipboard()
    except ClipboardError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not text.strip():
        print("Clipboard is empty; nothing was saved.", file=sys.stderr)
        return 2

    try:
        target = save_translation(args.project_dir, text, overwrite=args.overwrite, chunk_name=args.chunk)
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    project = Project.load(args.project_dir)
    relative_target = target.relative_to(project.project_dir)
    print(f"Saved {relative_target}")
    status = get_status(project.project_dir)
    if status.next_missing:
        print(f"Progress: {format_status(status)}")
        print(f"Next: openlongpdf next {_shell_quote(project.project_dir)} --copy --open chatgpt")
    else:
        print(f"All chunks translated. Run: openlongpdf assemble {_shell_quote(project.project_dir)}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    saved_paths = import_pack_response_file(args.project_dir, args.response_file, overwrite=args.overwrite)
    project = Project.load(args.project_dir)
    print(f"Imported {len(saved_paths)} translated chunks.")
    for path in saved_paths:
        print(f"- {path.relative_to(project.project_dir)}")
    status = get_status(project.project_dir)
    if status.next_missing:
        print(f"Progress: {format_status(status)}")
    else:
        print(f"All chunks translated. Run: openlongpdf assemble {_shell_quote(project.project_dir)}")
    return 0


def cmd_translate(args: argparse.Namespace) -> int:
    plan = plan_translation(args.project_dir, overwrite=args.overwrite, limit=args.limit)
    print(f"{plan.chunks_to_translate} chunks will be translated out of {plan.total_chunks}.")
    print(f"Prompt characters: {plan.prompt_chars}")
    print(f"Model: {args.model}")
    print(f"Base URL: {args.base_url}")
    if not args.yes:
        print("This may incur API charges. Re-run with --yes to start.")
        return 0

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"Missing API key. Set {args.api_key_env} before running translate.", file=sys.stderr)
        return 2

    config = ApiTranslationConfig(
        model=args.model,
        api_key=api_key,
        base_url=args.base_url,
        temperature=args.temperature,
        timeout=args.timeout,
        max_output_tokens=args.max_output_tokens,
        retries=args.retries,
    )

    result = translate_project(
        args.project_dir,
        client=OpenAICompatibleClient(),
        config=config,
        yes=True,
        overwrite=args.overwrite,
        limit=args.limit,
    )
    print(f"Saved {len(result.saved_paths)} translated chunks.")
    project = Project.load(args.project_dir)
    for path in result.saved_paths:
        print(f"- {path.relative_to(project.project_dir)}")
    status = get_status(project.project_dir)
    if status.next_missing:
        print(f"Progress: {format_status(status)}")
    else:
        print(f"All chunks translated. Run: openlongpdf assemble {_shell_quote(project.project_dir)}")
    return 0


def cmd_assemble(args: argparse.Namespace) -> int:
    outputs = assemble_project(args.project_dir)
    print(f"Wrote {outputs.markdown_path}")
    print(f"Wrote {outputs.html_path}")
    return 0


def _shell_quote(value: str | Path) -> str:
    return shlex.quote(str(value))


def _resolve_pack_path(project: Project, pack: str) -> Path:
    raw = Path(pack).expanduser()
    if raw.exists():
        return raw
    filename = raw.name if raw.name.endswith(".md") else f"{raw.name}.md"
    path = project.project_dir / "output" / "packs" / filename
    if not path.exists():
        raise FileNotFoundError(f"Pack file not found: {path}")
    return path


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import html
import json
import re
import secrets
import socket
import urllib.parse
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .project import Project, format_status, get_status, import_pack_response, write_translation_packs
from .render import assemble_project
from .sizing import recommend_chunks_per_pack


PACK_RE = re.compile(r"^pack_\d{3}(?:\.md)?$")
CHATGPT_URL = "https://chatgpt.com/"
ASSIST_STATE_PATH = "output/assist_state.json"
ASSIST_STATUSES = {"pending", "sending", "sent", "imported", "failed"}


@dataclass(frozen=True)
class AssistPack:
    name: str
    text: str
    response_path: str


@dataclass(frozen=True)
class AssistSummary:
    total: int
    pending: int
    sending: int
    sent: int
    imported: int
    failed: int
    next_pack: str | None
    last_error: str | None
    packs: dict[str, dict[str, object]]


@dataclass(frozen=True)
class AssistImportResult:
    ok: bool
    pack_name: str
    response_path: Path
    imported_chunk_names: list[str]
    assembled: bool
    markdown_path: Path | None = None
    html_path: Path | None = None
    error: str | None = None


def run_gui(project_dir: str | Path, *, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    root = Path(project_dir).expanduser()
    Project.load(root)
    server_port = _find_free_port(host, port)
    base_url = f"http://{host}:{server_port}"
    assist_token = secrets.token_urlsafe(18)
    handler = _make_handler(root, base_url=base_url, assist_token=assist_token)
    server = ThreadingHTTPServer((host, server_port), handler)
    url = f"{base_url}/"
    print(f"OpenLongPDF GUI: {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping OpenLongPDF GUI.")
    finally:
        server.server_close()


def render_dashboard(project_dir: str | Path, *, message: str = "") -> str:
    project = Project.load(project_dir)
    status = get_status(project.project_dir)
    recommendation = recommend_chunks_per_pack(project.project_dir)
    packs = sorted((project.project_dir / "output" / "packs").glob("pack_*.md"))
    assist_summary = get_assist_summary(project.project_dir)
    pack_items = "\n".join(_render_pack_item(project, path) for path in packs)
    if not pack_items:
        pack_items = "<p>No packs yet. Generate packs below.</p>"
    output_dir = project.project_dir / "output"
    reading_note = output_dir / "reading_note.md"
    index_html = output_dir / "index.html"
    message_html = f'<p class="message">{html.escape(message)}</p>' if message else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OpenLongPDF</title>
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.5; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 28px 18px 48px; }}
    h1, h2 {{ line-height: 1.2; }}
    .meta, .message, .panel {{ border: 1px solid #d4d7dd; border-radius: 8px; padding: 14px; margin: 14px 0; }}
    .message {{ background: #ecfdf5; border-color: #86efac; }}
    .pack {{ border-top: 1px solid #d4d7dd; padding: 16px 0; }}
    button, input, textarea {{ font: inherit; }}
    button {{ padding: 8px 12px; border-radius: 6px; border: 1px solid #6b7280; cursor: pointer; }}
    textarea {{ width: 100%; min-height: 180px; box-sizing: border-box; }}
    input[type="number"] {{ width: 80px; }}
    code {{ word-break: break-all; }}
    .actions {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    .muted {{ color: #6b7280; }}
    .failed {{ color: #b91c1c; }}
    .primary-action {{ display: inline-block; padding: 12px 16px; border: 1px solid #111827; border-radius: 6px; background: #111827; color: #fff; text-decoration: none; font-weight: 700; }}
    summary {{ cursor: pointer; font-weight: 700; }}
  </style>
</head>
<body>
<main>
  <h1>OpenLongPDF</h1>
  {message_html}

  <section class="panel">
    <h2>Ready</h2>
    <p>Use ChatGPT to translate this PDF automatically.</p>
    <p><a class="primary-action" href="/assist">Start ChatGPT Translation</a></p>
  </section>

  <details class="panel">
    <summary>Advanced</summary>
    <section class="meta">
      <p><strong>Project:</strong> <code>{html.escape(str(project.project_dir))}</code></p>
      <p><strong>Source:</strong> <code>{html.escape(project.source_pdf)}</code></p>
      <p><strong>Status:</strong> {html.escape(format_status(status))}</p>
    </section>

    <h2>Generate Packs</h2>
    <form method="post" action="/pack" class="actions">
      <label>Chunks per pack <input name="chunks_per_pack" type="number" min="1" value="{recommendation.chunks_per_pack}"></label>
      <button type="submit">Generate Packs</button>
    </form>
    <p class="muted"><strong>Recommended:</strong> {recommendation.chunks_per_pack} chunks per pack, about {recommendation.estimated_packs} packs. This uses conservative ChatGPT-app sized budgets; if output is truncated, regenerate with fewer chunks per pack.</p>

    <h2>Packs</h2>
    <p><a href="/assist">Browser Assist</a> can add a ChatGPT-side helper that sends queued packs, captures ChatGPT replies, imports them, and assembles the finished notes.</p>
    {_render_assist_progress(assist_summary)}
    {pack_items}

    <h2>Assemble</h2>
    <form method="post" action="/assemble">
      <button type="submit">Assemble Reading Notes</button>
    </form>
    <p>Markdown: <code>{html.escape(str(reading_note))}</code></p>
    <p>HTML: <code>{html.escape(str(index_html))}</code></p>
  </details>
</main>
<script>
async function copyPack(packName) {{
  const response = await fetch(`/pack/${{encodeURIComponent(packName + ".md")}}`);
  if (!response.ok) {{
    alert("Could not read pack text.");
    return;
  }}
  const text = await response.text();
  await navigator.clipboard.writeText(text);
  alert(`${{packName}} copied to clipboard.`);
}}
</script>
</body>
</html>
"""


def resolve_pack_path(project_dir: str | Path, pack_name: str) -> Path:
    if not PACK_RE.fullmatch(pack_name):
        raise ValueError(f"Invalid pack name: {pack_name}")
    filename = pack_name if pack_name.endswith(".md") else f"{pack_name}.md"
    path = Project.load(project_dir).project_dir / "output" / "packs" / filename
    if not path.exists():
        raise FileNotFoundError(f"Pack file not found: {path}")
    return path


def import_response_text(project_dir: str | Path, response_text: str) -> list[Path]:
    if not response_text.strip():
        raise ValueError("Translated response is empty")
    return import_pack_response(project_dir, response_text)


def get_assist_summary(project_dir: str | Path) -> AssistSummary:
    project = Project.load(project_dir)
    state = _read_assist_state(project.project_dir)
    packs = state["packs"]
    failed_record = next((record for record in packs.values() if record["status"] == "failed"), None)
    next_pack = None
    if failed_record is None:
        for name, record in packs.items():
            if record["status"] == "pending":
                next_pack = name
                break
    return AssistSummary(
        total=len(packs),
        pending=sum(1 for record in packs.values() if record["status"] == "pending"),
        sending=sum(1 for record in packs.values() if record["status"] == "sending"),
        sent=sum(1 for record in packs.values() if record["status"] == "sent"),
        imported=sum(1 for record in packs.values() if record["status"] == "imported"),
        failed=sum(1 for record in packs.values() if record["status"] == "failed"),
        next_pack=next_pack,
        last_error=str(failed_record.get("last_error") or "") if failed_record else None,
        packs=packs,
    )


def import_assist_pack_response(project_dir: str | Path, pack_name: str, response_text: str) -> AssistImportResult:
    project = Project.load(project_dir)
    pack_path = resolve_pack_path(project.project_dir, pack_name)
    normalized_pack = pack_path.stem
    response_dir = project.project_dir / "output" / "pack_responses"
    response_dir.mkdir(parents=True, exist_ok=True)
    response_path = response_dir / f"{normalized_pack}_response.md"
    failed_path = response_dir / f"{normalized_pack}_failed_response.md"
    raw_text = response_text.rstrip() + "\n"

    try:
        if not response_text.strip():
            raise ValueError("Translated response is empty")
        saved_paths = import_pack_response(project.project_dir, response_text)
    except (FileExistsError, ValueError, RuntimeError) as exc:
        failed_path.write_text(raw_text, encoding="utf-8")
        _set_assist_pack_state(
            project.project_dir,
            normalized_pack,
            "failed",
            last_error=str(exc),
            response_path=_project_relative(project, failed_path),
            imported_chunk_names=[],
        )
        return AssistImportResult(
            ok=False,
            pack_name=normalized_pack,
            response_path=failed_path,
            imported_chunk_names=[],
            assembled=False,
            error=str(exc),
        )

    response_path.write_text(raw_text, encoding="utf-8")
    imported_chunk_names = [path.name.removesuffix("_translated.md") for path in saved_paths]
    _set_assist_pack_state(
        project.project_dir,
        normalized_pack,
        "imported",
        last_error="",
        response_path=_project_relative(project, response_path),
        imported_chunk_names=imported_chunk_names,
    )
    assembled = False
    markdown_path = None
    html_path = None
    if _all_assist_packs_imported(project.project_dir) and get_status(project.project_dir).remaining_chunks == 0:
        outputs = assemble_project(project.project_dir)
        assembled = True
        markdown_path = outputs.markdown_path
        html_path = outputs.html_path
    return AssistImportResult(
        ok=True,
        pack_name=normalized_pack,
        response_path=response_path,
        imported_chunk_names=imported_chunk_names,
        assembled=assembled,
        markdown_path=markdown_path,
        html_path=html_path,
    )


def render_browser_assist(
    project_dir: str | Path,
    *,
    base_url: str = "http://127.0.0.1:8765",
    token: str = "",
) -> str:
    project = Project.load(project_dir)
    packs = sorted((project.project_dir / "output" / "packs").glob("pack_*.md"))
    summary = get_assist_summary(project.project_dir)
    next_pack = next_assist_pack(project.project_dir)
    next_text = next_pack.name if next_pack else "none"
    bookmarklet = _build_bookmarklet(base_url=base_url, token=token)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OpenLongPDF Browser Assist</title>
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.5; }}
    main {{ max-width: 900px; margin: 0 auto; padding: 28px 18px 48px; }}
    .panel {{ border: 1px solid #d4d7dd; border-radius: 8px; padding: 14px; margin: 14px 0; }}
    textarea {{ width: 100%; min-height: 130px; box-sizing: border-box; }}
    code {{ word-break: break-all; }}
    .bookmarklet {{ display: inline-block; padding: 8px 12px; border: 1px solid #6b7280; border-radius: 6px; text-decoration: none; }}
    .primary-action {{ display: inline-block; padding: 12px 16px; border: 1px solid #111827; border-radius: 6px; background: #111827; color: #fff; text-decoration: none; font-weight: 700; }}
    .muted {{ color: #6b7280; }}
    summary {{ cursor: pointer; font-weight: 700; }}
  </style>
</head>
<body>
<main>
  <h1>OpenLongPDF Assist</h1>
  <section class="panel">
    <p>Drag this button to your bookmarks bar. Open ChatGPT, then click it once.</p>
    <p><a class="primary-action" href="{html.escape(bookmarklet)}">OpenLongPDF Assist</a></p>
  </section>
  <details class="panel">
    <summary>Advanced</summary>
    <p>Project: <code>{html.escape(str(project.project_dir))}</code></p>
    <p>Packs: {len(packs)} generated. Next unsent pack: <strong>{html.escape(next_text)}</strong>.</p>
    <p>Assist state: {summary.pending} pending, {summary.sent} sent, {summary.imported} imported, {summary.failed} failed.</p>
    <p>The helper adds two visible buttons on ChatGPT: <strong>Send next OpenLongPDF pack</strong> and <strong>Auto-send, capture, import, and assemble remaining packs</strong>.</p>
    <p>Auto mode asks for one-time consent at the beginning of the session. After that consent, it sends each remaining pack, waits for ChatGPT to finish, extracts the new assistant response, posts it back to <code>/assist/import-response</code>, imports translated chunks, and assembles the final notes when all packs are imported.</p>
    <p>It does not store ChatGPT credentials, cookies, access tokens, or session data.</p>
    <textarea readonly>{html.escape(bookmarklet)}</textarea>
    <p><a href="/">Back to project</a></p>
  </details>
</main>
</body>
</html>
"""


def next_assist_pack(project_dir: str | Path) -> AssistPack | None:
    project = Project.load(project_dir)
    summary = get_assist_summary(project.project_dir)
    if summary.failed:
        return None
    for path in sorted((project.project_dir / "output" / "packs").glob("pack_*.md")):
        record = summary.packs.get(path.stem, {})
        if record.get("status") != "pending":
            continue
        response_path = project.project_dir / "output" / "pack_responses" / f"{path.stem}_response.md"
        return AssistPack(
            name=path.stem,
            text=path.read_text(encoding="utf-8"),
            response_path=str(response_path.relative_to(project.project_dir)),
        )
    return None


def mark_assist_pack_sent(project_dir: str | Path, pack_name: str) -> None:
    _set_assist_pack_state(project_dir, pack_name, "sent")


def mark_assist_pack_sending(project_dir: str | Path, pack_name: str) -> None:
    _set_assist_pack_state(project_dir, pack_name, "sending")


def mark_assist_pack_failed(project_dir: str | Path, pack_name: str, error: str) -> None:
    project = Project.load(project_dir)
    pack_path = resolve_pack_path(project.project_dir, pack_name)
    failed_path = project.project_dir / "output" / "pack_responses" / f"{pack_path.stem}_failed_response.md"
    _set_assist_pack_state(
        project.project_dir,
        pack_path.stem,
        "failed",
        last_error=error,
        response_path=_project_relative(project, failed_path),
        imported_chunk_names=[],
    )


def retry_failed_assist_pack(project_dir: str | Path, pack_name: str | None = None) -> str:
    project = Project.load(project_dir)
    summary = get_assist_summary(project.project_dir)
    target = pack_name
    if target is None:
        for name, record in summary.packs.items():
            if record.get("status") == "failed":
                target = name
                break
    if target is None:
        raise ValueError("No failed assist pack to retry")
    record = summary.packs.get(target)
    if record is None:
        raise ValueError(f"Unknown pack: {target}")
    if record.get("status") != "failed":
        raise ValueError(f"Pack is not failed: {target}")
    _set_assist_pack_state(project.project_dir, target, "pending", last_error="", imported_chunk_names=[])
    return target


def reset_assist_state(project_dir: str | Path) -> None:
    project = Project.load(project_dir)
    packs = {}
    for pack_path in sorted((project.project_dir / "output" / "packs").glob("pack_*.md")):
        chunk_names = _pack_chunk_names(pack_path)
        imported_chunk_names = [name for name in chunk_names if _has_chunk_translation(project, name)]
        status = "imported" if chunk_names and len(imported_chunk_names) == len(chunk_names) else "pending"
        response_path = project.project_dir / "output" / "pack_responses" / f"{pack_path.stem}_response.md"
        packs[pack_path.stem] = _assist_record(
            status=status,
            response_path=_project_relative(project, response_path),
            imported_chunk_names=imported_chunk_names if status == "imported" else [],
        )
    _write_assist_state(project.project_dir, {"packs": packs})


def _set_assist_pack_state(
    project_dir: str | Path,
    pack_name: str,
    status: str,
    *,
    last_error: str = "",
    response_path: str | None = None,
    imported_chunk_names: list[str] | None = None,
) -> None:
    if not PACK_RE.fullmatch(pack_name):
        raise ValueError(f"Invalid pack name: {pack_name}")
    project = Project.load(project_dir)
    pack_path = resolve_pack_path(project.project_dir, pack_name)
    if status not in ASSIST_STATUSES:
        raise ValueError(f"Invalid assist pack status: {status}")
    state = _read_assist_state(project.project_dir)
    packs = state["packs"]
    record = dict(packs.get(pack_path.stem, _assist_record()))
    record["status"] = status
    record["last_error"] = last_error
    if response_path is not None:
        record["response_path"] = response_path
    elif not record.get("response_path"):
        response = project.project_dir / "output" / "pack_responses" / f"{pack_path.stem}_response.md"
        record["response_path"] = _project_relative(project, response)
    if imported_chunk_names is not None:
        record["imported_chunk_names"] = imported_chunk_names
    packs[pack_path.stem] = record
    _write_assist_state(project.project_dir, state)


def _render_assist_progress(summary: AssistSummary) -> str:
    failed_html = ""
    if summary.failed:
        failed_items = []
        for pack_name, record in summary.packs.items():
            if record.get("status") != "failed":
                continue
            failed_items.append(
                "<li>"
                f"<strong>{html.escape(pack_name)}</strong>: {html.escape(str(record.get('last_error') or 'failed'))}"
                "</li>"
            )
        failed_html = (
            '<div class="failed"><p><strong>Failed packs need attention before auto-run can continue.</strong></p>'
            f"<ul>{''.join(failed_items)}</ul></div>"
            '<form method="post" action="/assist/retry-failed" class="actions">'
            '<button type="submit">Retry failed pack</button>'
            "</form>"
        )
    return f"""<div class="meta">
  <p><strong>Assist progress:</strong> {summary.total} packs total, {summary.pending} pending, {summary.sent} sent, {summary.imported} imported, {summary.failed} failed.</p>
  <p><strong>Next pack:</strong> {html.escape(summary.next_pack or "none")}</p>
  <form method="post" action="/assist/reset-state" class="actions">
    <button type="submit">Reset assist state</button>
  </form>
  {failed_html}
</div>"""


def _summary_payload(summary: AssistSummary) -> dict[str, object]:
    return {
        "total": summary.total,
        "pending": summary.pending,
        "sending": summary.sending,
        "sent": summary.sent,
        "imported": summary.imported,
        "failed": summary.failed,
        "nextPack": summary.next_pack,
        "lastError": summary.last_error,
    }


def _assist_import_payload(result: AssistImportResult) -> dict[str, object]:
    return {
        "ok": result.ok,
        "pack": result.pack_name,
        "responsePath": result.response_path.as_posix(),
        "importedChunkNames": result.imported_chunk_names,
        "assembled": result.assembled,
        "markdownPath": result.markdown_path.as_posix() if result.markdown_path else None,
        "htmlPath": result.html_path.as_posix() if result.html_path else None,
        "error": result.error,
    }


def _render_pack_item(project: Project, path: Path) -> str:
    pack = path.stem
    response_path = project.project_dir / "output" / "pack_responses" / f"{pack}_response.md"
    return f"""<div class="pack">
  <h3>{html.escape(pack)}</h3>
  <p>Prompt: <code>{html.escape(str(path.relative_to(project.project_dir)))}</code></p>
  <p>Response target: <code>{html.escape(str(response_path.relative_to(project.project_dir)))}</code></p>
  <div class="actions">
    <button type="button" data-pack="{html.escape(pack)}" onclick="copyPack(this.dataset.pack)">Copy Pack</button>
    <a href="https://chatgpt.com/" target="_blank" rel="noreferrer"><button type="button">Open ChatGPT</button></a>
  </div>
  <form method="post" action="/import">
    <input type="hidden" name="pack" value="{html.escape(pack)}">
    <p><label>Paste translated response</label></p>
    <textarea name="response_text" placeholder="Paste ChatGPT response with translated chunk markers here"></textarea>
    <p><button type="submit">Import Response</button></p>
  </form>
</div>"""


def _make_handler(project_dir: Path, *, base_url: str = "http://127.0.0.1:8765", assist_token: str = ""):
    class GuiHandler(BaseHTTPRequestHandler):
        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._send_cors_headers()
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            try:
                if parsed.path == "/":
                    query = urllib.parse.parse_qs(parsed.query)
                    message = query.get("message", [""])[-1]
                    self._send_html(render_dashboard(project_dir, message=message))
                    return
                if parsed.path == "/assist":
                    self._send_html(render_browser_assist(project_dir, base_url=base_url, token=assist_token))
                    return
                if parsed.path == "/assist/next.json":
                    self._require_assist_token(parsed)
                    summary = get_assist_summary(project_dir)
                    if summary.failed:
                        self._send_json(
                            {
                                "done": False,
                                "blocked": True,
                                "error": summary.last_error,
                                "state": _summary_payload(summary),
                            }
                        )
                        return
                    pack = next_assist_pack(project_dir)
                    if pack is None:
                        self._send_json({"done": True, "state": _summary_payload(summary)})
                    else:
                        self._send_json(
                            {
                                "done": False,
                                "pack": pack.name,
                                "text": pack.text,
                                "responsePath": pack.response_path,
                                "state": _summary_payload(summary),
                            }
                        )
                    return
                if parsed.path.startswith("/pack/"):
                    pack_name = urllib.parse.unquote(parsed.path.removeprefix("/pack/"))
                    text = resolve_pack_path(project_dir, pack_name).read_text(encoding="utf-8")
                    self._send_text(text)
                    return
                self.send_error(404)
            except PermissionError as exc:
                self.send_error(403, str(exc))
            except (FileNotFoundError, ValueError) as exc:
                self.send_error(400, str(exc))

        def do_POST(self) -> None:
            try:
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/assist/mark-sent":
                    self._require_assist_token(parsed)
                    fields = self._read_payload()
                    pack_name = fields.get("pack", "")
                    mark_assist_pack_sent(project_dir, pack_name)
                    self._send_json({"ok": True, "pack": pack_name})
                    return
                if parsed.path == "/assist/mark-sending":
                    self._require_assist_token(parsed)
                    fields = self._read_payload()
                    pack_name = fields.get("pack", "")
                    mark_assist_pack_sending(project_dir, pack_name)
                    self._send_json({"ok": True, "pack": pack_name})
                    return
                if parsed.path == "/assist/mark-failed":
                    self._require_assist_token(parsed)
                    fields = self._read_payload()
                    pack_name = fields.get("pack", "")
                    error = fields.get("error", "ChatGPT response capture failed")
                    mark_assist_pack_failed(project_dir, pack_name, error)
                    self._send_json({"ok": True, "pack": pack_name, "error": error})
                    return
                if parsed.path == "/assist/import-response":
                    self._require_assist_token(parsed)
                    fields = self._read_payload()
                    result = import_assist_pack_response(
                        project_dir,
                        fields.get("pack", ""),
                        fields.get("responseText") or fields.get("response_text", ""),
                    )
                    payload = _assist_import_payload(result)
                    self._send_json(payload, status=200 if result.ok else 400)
                    return
                fields = self._read_payload()
                if parsed.path == "/pack":
                    chunks_per_pack = int(fields.get("chunks_per_pack", "4"))
                    result = write_translation_packs(project_dir, chunks_per_pack=chunks_per_pack)
                    self._redirect(f"/?message={urllib.parse.quote(f'Generated {len(result.pack_paths)} packs')}")
                    return
                if parsed.path == "/import":
                    saved = import_response_text(project_dir, fields.get("response_text", ""))
                    self._redirect(f"/?message={urllib.parse.quote(f'Imported {len(saved)} translated chunks')}")
                    return
                if parsed.path == "/assemble":
                    outputs = assemble_project(project_dir)
                    self._redirect(f"/?message={urllib.parse.quote(f'Wrote {outputs.markdown_path.name} and {outputs.html_path.name}')}")
                    return
                if parsed.path == "/assist/reset-state":
                    reset_assist_state(project_dir)
                    self._redirect("/?message=Assist%20state%20reset")
                    return
                if parsed.path == "/assist/retry-failed":
                    retried = retry_failed_assist_pack(project_dir)
                    self._redirect(f"/?message={urllib.parse.quote(f'Retrying {retried}')}")
                    return
                self.send_error(404)
            except PermissionError as exc:
                self.send_error(403, str(exc))
            except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
                self._send_html(render_dashboard(project_dir, message=f"Error: {exc}"), status=400)

        def log_message(self, format: str, *args) -> None:
            return

        def _read_form(self) -> dict[str, str]:
            length = int(self.headers.get("Content-Length", "0"))
            data = self.rfile.read(length).decode("utf-8")
            parsed = urllib.parse.parse_qs(data, keep_blank_values=True)
            return {key: values[-1] for key, values in parsed.items()}

        def _read_payload(self) -> dict[str, str]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            content_type = self.headers.get("Content-Type", "")
            if "application/json" in content_type:
                data = json.loads(raw or "{}")
                return {str(key): "" if value is None else str(value) for key, value in data.items()}
            parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
            return {key: values[-1] for key, values in parsed.items()}

        def _send_html(self, body: str, *, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def _send_text(self, body: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def _send_json(self, data: dict[str, object], *, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write((json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))

        def _redirect(self, location: str) -> None:
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def _send_cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "https://chatgpt.com")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _require_assist_token(self, parsed: urllib.parse.ParseResult) -> None:
            query = urllib.parse.parse_qs(parsed.query)
            provided = query.get("token", [""])[-1]
            if not assist_token or not secrets.compare_digest(provided, assist_token):
                raise PermissionError("Invalid browser assist token")

    return GuiHandler


def _find_free_port(host: str, start_port: int) -> int:
    for port in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free port found starting at {start_port}")


def _read_assist_state(project_dir: Path) -> dict[str, object]:
    project = Project.load(project_dir)
    path = project.project_dir / ASSIST_STATE_PATH
    if not path.exists():
        return _normalize_assist_state(project, {})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _normalize_assist_state(project, {})
    return _normalize_assist_state(project, data)


def _write_assist_state(project_dir: Path, state: dict[str, object]) -> None:
    path = project_dir / ASSIST_STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_assist_state(project: Project, raw_state: dict[str, object]) -> dict[str, object]:
    raw_packs = raw_state.get("packs", {})
    if not isinstance(raw_packs, dict):
        raw_packs = {}
    old_sent = raw_state.get("sent_packs", [])
    if not isinstance(old_sent, list):
        old_sent = []
    old_sent_packs = {str(item) for item in old_sent}

    packs: dict[str, dict[str, object]] = {}
    for pack_path in sorted((project.project_dir / "output" / "packs").glob("pack_*.md")):
        name = pack_path.stem
        raw_record = raw_packs.get(name, {})
        if not isinstance(raw_record, dict):
            raw_record = {}
        chunk_names = _pack_chunk_names(pack_path)
        imported_chunk_names = [chunk_name for chunk_name in chunk_names if _has_chunk_translation(project, chunk_name)]
        default_response = project.project_dir / "output" / "pack_responses" / f"{name}_response.md"
        status = str(raw_record.get("status") or ("sent" if name in old_sent_packs else "pending"))
        if status not in ASSIST_STATUSES:
            status = "pending"
        if chunk_names and len(imported_chunk_names) == len(chunk_names):
            status = "imported"
        record_imported = raw_record.get("imported_chunk_names", [])
        if not isinstance(record_imported, list):
            record_imported = []
        if status == "imported":
            record_imported = imported_chunk_names
        packs[name] = _assist_record(
            status=status,
            last_error=str(raw_record.get("last_error") or ""),
            response_path=str(raw_record.get("response_path") or _project_relative(project, default_response)),
            imported_chunk_names=[str(item) for item in record_imported],
        )
    return {"version": 1, "packs": packs, "updated_at": str(raw_state.get("updated_at") or "")}


def _assist_record(
    *,
    status: str = "pending",
    last_error: str = "",
    response_path: str = "",
    imported_chunk_names: list[str] | None = None,
) -> dict[str, object]:
    return {
        "status": status,
        "last_error": last_error,
        "response_path": response_path,
        "imported_chunk_names": imported_chunk_names or [],
    }


def _pack_chunk_names(pack_path: Path) -> list[str]:
    text = pack_path.read_text(encoding="utf-8")
    names = re.findall(r"--- BEGIN SOURCE CHUNK (chunk_\d{3}) ---", text)
    if names:
        return names
    match = re.search(r"Chunks in this pack:\s*(?P<names>chunk_\d{3}(?:,\s*chunk_\d{3})*)", text)
    if not match:
        return []
    return [name.strip() for name in match.group("names").split(",")]


def _has_chunk_translation(project: Project, chunk_name: str) -> bool:
    for chunk in project.chunks:
        if chunk.name != chunk_name:
            continue
        path = project.abs_path(chunk.translated_path)
        return path.exists() and bool(path.read_text(encoding="utf-8").strip())
    return False


def _all_assist_packs_imported(project_dir: str | Path) -> bool:
    summary = get_assist_summary(project_dir)
    return summary.total > 0 and summary.imported == summary.total


def _project_relative(project: Project, path: Path) -> str:
    return path.relative_to(project.project_dir).as_posix()


def _build_bookmarklet(*, base_url: str, token: str) -> str:
    script = f"""
(() => {{
  const server = {json.dumps(base_url)};
  const token = {json.dumps(token)};
  const chatgptUrl = {json.dumps(CHATGPT_URL)};
  const panelId = "openlongpdf-assist-panel";
  if (location.origin !== "https://chatgpt.com") {{
    window.open(chatgptUrl, "_blank", "noopener,noreferrer");
    alert("Open ChatGPT, then click the OpenLongPDF Assist bookmarklet again on that page.");
    return;
  }}
  let panel = document.getElementById(panelId);
  if (panel) {{
    panel.remove();
    return;
  }}
  panel = document.createElement("div");
  panel.id = panelId;
  panel.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;background:#111827;color:#f9fafb;border:1px solid #4b5563;border-radius:8px;padding:12px;font:14px system-ui;box-shadow:0 8px 24px rgba(0,0,0,.25);max-width:320px";
  panel.innerHTML = `
    <div style="font-weight:700;margin-bottom:8px">OpenLongPDF Assist</div>
    <button id="openlongpdf-send-next" style="margin:0 6px 6px 0;padding:6px 8px">Send next OpenLongPDF pack</button>
    <button id="openlongpdf-auto-send" style="margin:0 0 6px 0;padding:6px 8px">Auto-send, capture, import, and assemble remaining packs</button>
    <button id="openlongpdf-close" style="margin-left:6px;padding:6px 8px">Close</button>
    <div id="openlongpdf-status" style="margin-top:6px;color:#d1d5db">Ready.</div>
  `;
  document.body.appendChild(panel);
  const status = panel.querySelector("#openlongpdf-status");
  const setStatus = (text) => {{ status.textContent = text; }};
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function fetchNextPack() {{
    const response = await fetch(`${{server}}/assist/next.json?token=${{encodeURIComponent(token)}}`);
    if (!response.ok) throw new Error(`OpenLongPDF local server returned ${{response.status}}`);
    const data = await response.json();
    if (data.blocked) throw new Error(data.error || "OpenLongPDF is blocked by a failed pack. Retry it in the local GUI.");
    return data;
  }}
  async function postLocal(path, payload) {{
    const response = await fetch(`${{server}}${{path}}?token=${{encodeURIComponent(token)}}`, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(payload)
    }});
    const text = await response.text();
    let data = {{}};
    if (text) {{
      try {{ data = JSON.parse(text); }} catch (_error) {{ data = {{ error: text }}; }}
    }}
    if (!response.ok) throw new Error(data.error || `OpenLongPDF local server returned ${{response.status}}`);
    return data;
  }}
  async function markSending(packName) {{
    await postLocal("/assist/mark-sending", {{ pack: packName }});
  }}
  async function markSent(packName) {{
    await postLocal("/assist/mark-sent", {{ pack: packName }});
  }}
  async function markFailed(packName, error) {{
    if (!packName) return;
    try {{ await postLocal("/assist/mark-failed", {{ pack: packName, error: String(error.message || error) }}); }}
    catch (_error) {{}}
  }}
  async function importResponse(packName, responseText) {{
    return await postLocal("/assist/import-response", {{ pack: packName, responseText }});
  }}
  function composer() {{
    return document.querySelector("#prompt-textarea")
      || document.querySelector("textarea")
      || document.querySelector("[contenteditable='true']");
  }}
  function sendButton() {{
    return document.querySelector("[data-testid='send-button']")
      || document.querySelector("[data-testid='composer-send-button']")
      || document.querySelector("button[aria-label='Send prompt']")
      || Array.from(document.querySelectorAll("button")).find((button) => /send/i.test(button.getAttribute("aria-label") || ""));
  }}
  function stopButton() {{
    return document.querySelector("[data-testid='stop-button']")
      || Array.from(document.querySelectorAll("button")).find((button) => /stop/i.test(button.getAttribute("aria-label") || ""));
  }}
  function visibleText(node) {{
    if (!node) return "";
    const style = window.getComputedStyle(node);
    if (style.display === "none" || style.visibility === "hidden") return "";
    return (node.innerText || node.textContent || "").trim();
  }}
  function assistantNodes() {{
    const selectors = [
      "[data-message-author-role='assistant']",
      "article",
      ".markdown"
    ];
    for (const selector of selectors) {{
      const nodes = Array.from(document.querySelectorAll(selector)).filter((node) => visibleText(node));
      if (nodes.length) return nodes;
    }}
    const main = document.querySelector("main") || document.body;
    return Array.from(main.querySelectorAll("div")).filter((node) => visibleText(node).length > 100);
  }}
  function markdownishText(node) {{
    const clone = node.cloneNode(true);
    clone.querySelectorAll("pre").forEach((pre) => {{
      pre.textContent = `\\n\\`\\`\\`\\n${{pre.innerText || pre.textContent || ""}}\\n\\`\\`\\`\\n`;
    }});
    clone.querySelectorAll("li").forEach((li) => {{
      if (!/^[-*]\\s/.test(li.textContent || "")) li.textContent = `- ${{li.textContent || ""}}`;
    }});
    return visibleText(clone);
  }}
  function assistantTexts() {{
    return assistantNodes().map(markdownishText).filter(Boolean);
  }}
  function captureNewAssistantText(beforeTexts) {{
    const afterTexts = assistantTexts();
    if (afterTexts.length > beforeTexts.length) {{
      return afterTexts.slice(beforeTexts.length).join("\\n\\n").trim();
    }}
    if (afterTexts.length && afterTexts[afterTexts.length - 1] !== beforeTexts[beforeTexts.length - 1]) {{
      return afterTexts[afterTexts.length - 1].trim();
    }}
    return "";
  }}
  async function fillComposer(text) {{
    const target = composer();
    if (!target) throw new Error("ChatGPT composer was not found.");
    target.focus();
    if (target.tagName === "TEXTAREA") {{
      target.value = text;
      target.dispatchEvent(new Event("input", {{ bubbles: true }}));
      return;
    }}
    const data = new DataTransfer();
    data.setData("text/plain", text);
    target.dispatchEvent(new ClipboardEvent("paste", {{ clipboardData: data, bubbles: true, cancelable: true }}));
    await sleep(100);
    if (!target.textContent || target.textContent.length < Math.min(20, text.length)) {{
      target.textContent = text;
      target.dispatchEvent(new InputEvent("input", {{ bubbles: true, inputType: "insertText", data: text.slice(0, 1) }}));
    }}
  }}
  async function waitUntilIdle() {{
    const started = Date.now();
    while (Date.now() - started < 600000) {{
      if (!stopButton()) return;
      await sleep(1000);
    }}
    throw new Error("Timed out waiting for ChatGPT to finish responding.");
  }}
  async function waitForAssistantResponse(beforeTexts) {{
    const started = Date.now();
    let latest = "";
    while (Date.now() - started < 600000) {{
      const captured = captureNewAssistantText(beforeTexts);
      if (captured) latest = captured;
      if (latest && !stopButton()) {{
        await sleep(1200);
        return captureNewAssistantText(beforeTexts) || latest;
      }}
      await sleep(1000);
    }}
    throw new Error("Timed out waiting for a new ChatGPT assistant response.");
  }}
  async function sendOne({{ confirmFirst = true }} = {{}}) {{
    await waitUntilIdle();
    const pack = window.__openlongpdfNextPackOverride || await fetchNextPack();
    window.__openlongpdfNextPackOverride = null;
    if (pack.done) {{
      setStatus("No unsent packs remain.");
      return false;
    }}
    window.__openlongpdfCurrentPack = pack.pack;
    if (confirmFirst && !confirm(`Send ${{pack.pack}} to ChatGPT, capture the reply, import it locally, and assemble if this finishes the project?`)) return false;
    setStatus(`Filling ${{pack.pack}}...`);
    const beforeTexts = assistantTexts();
    await markSending(pack.pack);
    await fillComposer(pack.text);
    await sleep(250);
    const button = sendButton();
    if (!button || button.disabled) {{
      await navigator.clipboard.writeText(pack.text);
      throw new Error("Send button was unavailable. Pack text was copied to clipboard instead.");
    }}
    button.click();
    await markSent(pack.pack);
    setStatus(`Waiting for ChatGPT response to ${{pack.pack}}...`);
    const responseText = await waitForAssistantResponse(beforeTexts);
    if (!responseText.trim()) throw new Error(`Could not capture ChatGPT response for ${{pack.pack}}.`);
    setStatus(`Importing ${{pack.pack}} response...`);
    const imported = await importResponse(pack.pack, responseText);
    if (imported.assembled) {{
      setStatus(`Imported ${{pack.pack}} and assembled reading notes.`);
    }} else {{
      setStatus(`Imported ${{pack.pack}}: ${{imported.importedChunkNames.join(", ")}}.`);
    }}
    return true;
  }}
  panel.querySelector("#openlongpdf-send-next").onclick = async () => {{
    let currentPack = "";
    try {{
      const pack = await fetchNextPack();
      if (pack.done) {{ setStatus("No pending packs remain."); return; }}
      currentPack = pack.pack;
      window.__openlongpdfNextPackOverride = pack;
      await sendOne({{ confirmFirst: true }});
      window.__openlongpdfNextPackOverride = null;
    }}
    catch (error) {{ await markFailed(currentPack, error); setStatus(error.message); alert(error.message); }}
  }};
  panel.querySelector("#openlongpdf-auto-send").onclick = async () => {{
    if (!confirm("One-time consent: OpenLongPDF will send each remaining pack in this ChatGPT tab, capture each visible assistant reply, POST it to the local GUI for import, and assemble when all packs are imported. Keep this tab open. Continue?")) return;
    let currentPack = "";
    try {{
      while (true) {{
        const pack = await fetchNextPack();
        if (pack.done) {{ setStatus("All pending packs are imported or no pending packs remain."); break; }}
        currentPack = pack.pack;
        window.__openlongpdfNextPackOverride = pack;
        if (!(await sendOne({{ confirmFirst: false }}))) break;
        window.__openlongpdfNextPackOverride = null;
        await sleep(1500);
      }}
    }} catch (error) {{
      await markFailed(currentPack, error);
      setStatus(error.message);
      alert(error.message);
    }} finally {{
      window.__openlongpdfNextPackOverride = null;
    }}
  }};
  panel.querySelector("#openlongpdf-close").onclick = () => panel.remove();
}})();
"""
    compact = " ".join(line.strip() for line in script.splitlines() if line.strip())
    return "javascript:" + urllib.parse.quote(compact, safe="()")

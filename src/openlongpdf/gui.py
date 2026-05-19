from __future__ import annotations

import html
import json
import re
import secrets
import socket
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .project import Project, format_status, get_status, import_pack_response, write_translation_packs
from .render import assemble_project
from .sizing import recommend_chunks_per_pack


PACK_RE = re.compile(r"^pack_\d{3}(?:\.md)?$")
CHATGPT_URL = "https://chatgpt.com/"
ASSIST_STATE_PATH = "output/assist_state.json"


@dataclass(frozen=True)
class AssistPack:
    name: str
    text: str
    response_path: str


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
  </style>
</head>
<body>
<main>
  <h1>OpenLongPDF</h1>
  {message_html}
  <section class="meta">
    <p><strong>Project:</strong> <code>{html.escape(str(project.project_dir))}</code></p>
    <p><strong>Source:</strong> <code>{html.escape(project.source_pdf)}</code></p>
    <p><strong>Status:</strong> {html.escape(format_status(status))}</p>
  </section>

  <section class="panel">
    <h2>Generate Packs</h2>
    <form method="post" action="/pack" class="actions">
      <label>Chunks per pack <input name="chunks_per_pack" type="number" min="1" value="{recommendation.chunks_per_pack}"></label>
      <button type="submit">Generate Packs</button>
    </form>
    <p class="muted"><strong>Recommended:</strong> {recommendation.chunks_per_pack} chunks per pack, about {recommendation.estimated_packs} packs. This uses conservative ChatGPT-app sized budgets; if output is truncated, regenerate with fewer chunks per pack.</p>
  </section>

  <section class="panel">
    <h2>Packs</h2>
    <p><a href="/assist">Browser Assist</a> can add a ChatGPT-side button that sends queued packs from the ChatGPT page.</p>
    {pack_items}
  </section>

  <section class="panel">
    <h2>Assemble</h2>
    <form method="post" action="/assemble">
      <button type="submit">Assemble Reading Notes</button>
    </form>
    <p>Markdown: <code>{html.escape(str(reading_note))}</code></p>
    <p>HTML: <code>{html.escape(str(index_html))}</code></p>
  </section>
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


def render_browser_assist(
    project_dir: str | Path,
    *,
    base_url: str = "http://127.0.0.1:8765",
    token: str = "",
) -> str:
    project = Project.load(project_dir)
    packs = sorted((project.project_dir / "output" / "packs").glob("pack_*.md"))
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
    .muted {{ color: #6b7280; }}
  </style>
</head>
<body>
<main>
  <h1>Browser Assist</h1>
  <section class="panel">
    <p>Project: <code>{html.escape(str(project.project_dir))}</code></p>
    <p>Packs: {len(packs)} generated. Next unsent pack: <strong>{html.escape(next_text)}</strong>.</p>
  </section>
  <section class="panel">
    <h2>Install ChatGPT Helper</h2>
    <p>Drag this bookmarklet to your bookmarks bar, open ChatGPT, then click it on the ChatGPT page:</p>
    <p><a class="bookmarklet" href="{html.escape(bookmarklet)}">OpenLongPDF Assist</a></p>
    <textarea readonly>{html.escape(bookmarklet)}</textarea>
  </section>
  <section class="panel">
    <h2>What It Does</h2>
    <p>The helper adds two visible buttons on ChatGPT: <strong>Send next OpenLongPDF pack</strong> and <strong>Auto-send remaining packs</strong>.</p>
    <p>It fetches pack text from this local GUI, fills the ChatGPT composer, and clicks the send button only after you explicitly start it. It does not read ChatGPT responses, store credentials, cookies, or access tokens.</p>
    <p class="muted">Automatic sending depends on ChatGPT's visible page structure and may stop if the UI changes. When it stops, resend manually or use the one-pack button.</p>
  </section>
  <p><a href="/">Back to project</a> | <a href="{CHATGPT_URL}" target="_blank" rel="noreferrer">Open ChatGPT</a></p>
</main>
</body>
</html>
"""


def next_assist_pack(project_dir: str | Path) -> AssistPack | None:
    project = Project.load(project_dir)
    sent_packs = set(_read_assist_state(project.project_dir).get("sent_packs", []))
    for path in sorted((project.project_dir / "output" / "packs").glob("pack_*.md")):
        if path.stem in sent_packs:
            continue
        response_path = project.project_dir / "output" / "pack_responses" / f"{path.stem}_response.md"
        return AssistPack(
            name=path.stem,
            text=path.read_text(encoding="utf-8"),
            response_path=str(response_path.relative_to(project.project_dir)),
        )
    return None


def mark_assist_pack_sent(project_dir: str | Path, pack_name: str) -> None:
    if not PACK_RE.fullmatch(pack_name):
        raise ValueError(f"Invalid pack name: {pack_name}")
    project = Project.load(project_dir)
    resolve_pack_path(project.project_dir, pack_name)
    state = _read_assist_state(project.project_dir)
    sent_packs = list(state.get("sent_packs", []))
    if pack_name not in sent_packs:
        sent_packs.append(pack_name)
    state["sent_packs"] = sent_packs
    _write_assist_state(project.project_dir, state)


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
                    pack = next_assist_pack(project_dir)
                    if pack is None:
                        self._send_json({"done": True})
                    else:
                        self._send_json(
                            {
                                "done": False,
                                "pack": pack.name,
                                "text": pack.text,
                                "responsePath": pack.response_path,
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
                    fields = self._read_form()
                    pack_name = fields.get("pack", "")
                    mark_assist_pack_sent(project_dir, pack_name)
                    self._send_json({"ok": True, "pack": pack_name})
                    return
                fields = self._read_form()
                if self.path == "/pack":
                    chunks_per_pack = int(fields.get("chunks_per_pack", "4"))
                    result = write_translation_packs(project_dir, chunks_per_pack=chunks_per_pack)
                    self._redirect(f"/?message={urllib.parse.quote(f'Generated {len(result.pack_paths)} packs')}")
                    return
                if self.path == "/import":
                    saved = import_response_text(project_dir, fields.get("response_text", ""))
                    self._redirect(f"/?message={urllib.parse.quote(f'Imported {len(saved)} translated chunks')}")
                    return
                if self.path == "/assemble":
                    outputs = assemble_project(project_dir)
                    self._redirect(f"/?message={urllib.parse.quote(f'Wrote {outputs.markdown_path.name} and {outputs.html_path.name}')}")
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

        def _send_json(self, data: dict[str, object]) -> None:
            self.send_response(200)
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
    path = project_dir / ASSIST_STATE_PATH
    if not path.exists():
        return {"sent_packs": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    sent_packs = data.get("sent_packs", [])
    if not isinstance(sent_packs, list):
        return {"sent_packs": []}
    return {"sent_packs": [str(item) for item in sent_packs]}


def _write_assist_state(project_dir: Path, state: dict[str, object]) -> None:
    path = project_dir / ASSIST_STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    <button id="openlongpdf-auto-send" style="margin:0 0 6px 0;padding:6px 8px">Auto-send remaining packs</button>
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
    return await response.json();
  }}
  async function markSent(packName) {{
    const body = new URLSearchParams({{ pack: packName }});
    const response = await fetch(`${{server}}/assist/mark-sent?token=${{encodeURIComponent(token)}}`, {{
      method: "POST",
      headers: {{ "Content-Type": "application/x-www-form-urlencoded" }},
      body
    }});
    if (!response.ok) throw new Error(`Could not mark ${{packName}} as sent`);
  }}
  function composer() {{
    return document.querySelector("#prompt-textarea")
      || document.querySelector("textarea")
      || document.querySelector("[contenteditable='true']");
  }}
  function sendButton() {{
    return document.querySelector("[data-testid='send-button']")
      || document.querySelector("button[aria-label='Send prompt']")
      || Array.from(document.querySelectorAll("button")).find((button) => /send/i.test(button.getAttribute("aria-label") || ""));
  }}
  function stopButton() {{
    return document.querySelector("[data-testid='stop-button']")
      || Array.from(document.querySelectorAll("button")).find((button) => /stop/i.test(button.getAttribute("aria-label") || ""));
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
  async function sendOne({{ confirmFirst = true }} = {{}}) {{
    await waitUntilIdle();
    const pack = await fetchNextPack();
    if (pack.done) {{
      setStatus("No unsent packs remain.");
      return false;
    }}
    if (confirmFirst && !confirm(`Send ${{pack.pack}} to ChatGPT?`)) return false;
    setStatus(`Filling ${{pack.pack}}...`);
    await fillComposer(pack.text);
    await sleep(250);
    const button = sendButton();
    if (!button || button.disabled) {{
      await navigator.clipboard.writeText(pack.text);
      throw new Error("Send button was unavailable. Pack text was copied to clipboard instead.");
    }}
    button.click();
    await markSent(pack.pack);
    setStatus(`Sent ${{pack.pack}}. Save response to ${{pack.responsePath}}.`);
    return true;
  }}
  panel.querySelector("#openlongpdf-send-next").onclick = async () => {{
    try {{ await sendOne({{ confirmFirst: true }}); }}
    catch (error) {{ setStatus(error.message); alert(error.message); }}
  }};
  panel.querySelector("#openlongpdf-auto-send").onclick = async () => {{
    if (!confirm("Auto-send remaining OpenLongPDF packs? Keep this ChatGPT tab open. The helper stops at the first error.")) return;
    try {{
      while (await sendOne({{ confirmFirst: false }})) {{
        await sleep(1500);
      }}
    }} catch (error) {{
      setStatus(error.message);
      alert(error.message);
    }}
  }};
  panel.querySelector("#openlongpdf-close").onclick = () => panel.remove();
}})();
"""
    compact = " ".join(line.strip() for line in script.splitlines() if line.strip())
    return "javascript:" + urllib.parse.quote(compact, safe="()")

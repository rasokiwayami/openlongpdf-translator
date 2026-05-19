from __future__ import annotations

import html
import re
import socket
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .project import Project, format_status, get_status, import_pack_response, write_translation_packs
from .render import assemble_project


PACK_RE = re.compile(r"^pack_\d{3}(?:\.md)?$")


def run_gui(project_dir: str | Path, *, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    root = Path(project_dir).expanduser()
    Project.load(root)
    server_port = _find_free_port(host, port)
    handler = _make_handler(root)
    server = ThreadingHTTPServer((host, server_port), handler)
    url = f"http://{host}:{server_port}/"
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
      <label>Chunks per pack <input name="chunks_per_pack" type="number" min="1" value="4"></label>
      <button type="submit">Generate Packs</button>
    </form>
    <p class="muted">Use larger packs for fewer ChatGPT round trips. If ChatGPT truncates output, regenerate with fewer chunks per pack.</p>
  </section>

  <section class="panel">
    <h2>Packs</h2>
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


def _make_handler(project_dir: Path):
    class GuiHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            try:
                if parsed.path == "/":
                    query = urllib.parse.parse_qs(parsed.query)
                    message = query.get("message", [""])[-1]
                    self._send_html(render_dashboard(project_dir, message=message))
                    return
                if parsed.path.startswith("/pack/"):
                    pack_name = urllib.parse.unquote(parsed.path.removeprefix("/pack/"))
                    text = resolve_pack_path(project_dir, pack_name).read_text(encoding="utf-8")
                    self._send_text(text)
                    return
                self.send_error(404)
            except (FileNotFoundError, ValueError) as exc:
                self.send_error(400, str(exc))

        def do_POST(self) -> None:
            try:
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

        def _redirect(self, location: str) -> None:
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

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

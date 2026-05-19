# CLI Goal Prompt

Copy this into a Codex CLI session at the start. If `/goal` is available, use it with the main goal. If `/goal` is not available, paste the full block as the first message.

```text
AUTHORITATIVE ACTIVE GOAL:
Build the MVP of an OSS CLI tool named `openlongpdf` / `OpenLongPDF Translator`.

The product is a local-first workflow tool for long foreign-language PDFs. It extracts page-aware text, splits it into manageable chunks, generates prompts for AI translators, helps users send those prompts to the AI tools they already pay for, accepts translated chunks back, and assembles Markdown/HTML reading notes.

Core positioning:
- Turn long foreign-language PDFs into page-aware reading notes.
- No cloud lock-in.
- No extra translation subscription required.
- Use the ChatGPT/Claude/Gemini/DeepL account the user already has through a local GUI, with paid API automation as an optional advanced route.
- The tool is not a translation model.
- The tool must not publish or distribute copyrighted translated content.
- Demos/tests must use public-domain or synthetic sample text.

Important UX requirement:
Manual paste workflow is a first-class feature, not an afterthought.

Implement a paste-assist workflow:
1. The tool knows which chunk is next.
2. It can copy the next prompt to the clipboard.
3. It can open ChatGPT/Claude/Gemini in the browser.
4. It can show the exact file where the translated answer should be saved.
5. It can accept clipboard content and save it to the correct translated chunk file.
6. It can provide a local browser GUI for copying packs, opening ChatGPT, importing responses, and assembling notes.
7. It can automatically send missing chunks to a paid OpenAI-compatible API when the user provides an API key and `--yes`.
8. It can update status after each saved translation.

Do not build unsupported scraping of ChatGPT output in MVP.
Do not bypass rate limits, login walls, CAPTCHAs, usage limits, or UI protections.
Do not store ChatGPT credentials, cookies, access tokens, or session data.
If browser assistance is added, it must be explicit opt-in, visible to the user, and user-controlled.

Full automatic translation of all chunks must use official/OpenAI-compatible provider APIs, not unattended ChatGPT Web automation.

Automation design to preserve in code structure:
- `openlongpdf translate <project_dir> --model <model>`
- `openlongpdf translate <project_dir> --model <model> --base-url <url> --api-key-env <env>`

Auth rules:
- ChatGPT Plus/Pro subscription is not API authentication.
- True unattended batch translation requires official API credentials.
- Do not store ChatGPT browser cookies, sessions, passwords, or access tokens.
- Prefer environment variables first.
- If local config is added later, keep it explicit and documented.
- If OS keyring is available later, it can be used as an optional safer storage backend.

CLI commands to implement:

1. `openlongpdf prepare <pdf>`
   - Extract text page by page from a text-layer PDF.
   - Preserve original page numbers.
   - Split into chunks.
   - Default: 10 pages per chunk.
   - Support `--pages-per-chunk`.
   - Create:
     - `source_chunks/`
     - `prompts/`
     - `translated_chunks/`
     - `output/`
     - `status.json`
     - `manifest.md`

2. `openlongpdf status <project_dir>`
   - Show:
     - total chunks
     - translated chunks
     - remaining chunks
     - next missing chunk
   - Example:
     `34 chunks total, 12 translated, 22 remaining, next: chunk_013_translated.md`

3. `openlongpdf next <project_dir>`
   - Print the next prompt path.
   - Print the next translated chunk target path.
   - With `--copy`, copy the next prompt to clipboard.
   - With `--print`, print the prompt text to stdout.
   - With `--open chatgpt|claude|gemini`, open the selected service URL in the browser after copying the prompt.

4. `openlongpdf paste <project_dir>`
   - Read current clipboard text.
   - Save it into the next missing translated chunk file.
   - Refuse to overwrite an existing translated chunk unless `--overwrite` is passed.
   - Update `status.json`.
   - Print the next command the user should run.

5. `openlongpdf queue <project_dir>`
   - Show all remaining chunks, prompt files, and matching translation target files.
   - With `--all`, include chunks that already have translations.
   - With `--write`, create `output/translation_queue.md` as a checklist.
   - This is required for long documents so users can see the whole 30+ chunk workload up front instead of discovering one file at a time.

6. `openlongpdf pack <project_dir>`
   - Group remaining chunks into larger prompt files under `output/packs/`.
   - Default to a small number of chunks per pack and support `--chunks-per-pack`.
   - Write `output/translation_packs.md` with each pack file and suggested response save path.
   - Include a `copy-pack` command for each pack in `output/translation_packs.md`.
   - Require marked translated chunk blocks so multiple chunks can be imported safely.

7. `openlongpdf copy-pack <project_dir> <pack>`
   - Copy a pack file such as `pack_001` or `pack_001.md` to the clipboard.
   - With `--open chatgpt|claude|gemini`, open the selected service URL after copying.
   - On WSL/Windows, prefer PowerShell `Set-Clipboard` over `clip.exe` so Cyrillic, Japanese, and other non-ASCII text is preserved.

8. `openlongpdf import <project_dir> <response_file>`
   - Read a marked multi-chunk response saved by the user.
   - Save each marked block to the matching `translated_chunks/chunk_NNN_translated.md`.
   - Refuse to overwrite existing translated chunks unless `--overwrite` is passed.
   - Avoid partial imports by checking targets before writing.

9. `openlongpdf assemble <project_dir>`
   - Read translated chunks in order.
   - Generate:
     - `output/reading_note.md`
     - `output/index.html`
   - HTML should be simple but good-looking:
     - readable width
     - chunk navigation
     - page headings
     - table of contents
     - escaped user content
     - no frontend framework

10. `openlongpdf translate <project_dir> --model <model>`
   - Load missing chunks.
   - Read the API key from `OPENAI_API_KEY` by default.
   - Support `--base-url` for OpenAI-compatible providers.
   - Print the planned chunk count and prompt character count.
   - Refuse to call the paid API unless `--yes` is passed.
   - Save each API result immediately to `translated_chunks/`.
   - Resume safely by skipping already translated chunks.
   - Refuse to overwrite existing translated chunks unless `--overwrite` is passed.

11. `openlongpdf gui <project_dir>`
   - Start a local browser GUI for a prepared project.
   - Show project status and output paths.
   - Generate packs from the browser.
   - Copy pack text through the browser clipboard API.
   - Open ChatGPT in a new tab.
   - Let the user paste a translated response and import it.
   - Assemble Markdown/HTML outputs.
   - Do not scrape ChatGPT, store credentials, or automate browser submission.

12. Optional:
   `openlongpdf estimate <pdf>`
   - Show page count, extracted characters, estimated chunks, rough token estimate, and rough API cost placeholders.

13. Future:
   `openlongpdf auth <provider>`
   - Configure official API credentials for OpenAI, DeepL, or other providers.
   - Do not authenticate against ChatGPT Web accounts.

Implementation constraints:
- Python CLI.
- Keep dependencies small.
- Use `pypdf` for PDF extraction unless there is a clearly better lightweight option.
- Use `argparse` or `typer`; prefer the simpler working choice.
- Use UTF-8 everywhere.
- Must handle Japanese/Russian filenames on Windows.
- Windows support is a hard requirement.
- No OCR in MVP.
- No hosted web app.
- No native app.
- No user accounts.
- No billing.
- No cloud storage.
- No PDF regeneration.
- No fully automated ChatGPT scraping.
- No unattended ChatGPT Web bulk submission.

Recommended project structure:
- `pyproject.toml`
- `src/openlongpdf/__init__.py`
- `src/openlongpdf/cli.py`
- `src/openlongpdf/pdf_extract.py`
- `src/openlongpdf/chunking.py`
- `src/openlongpdf/prompts.py`
- `src/openlongpdf/project.py`
- `src/openlongpdf/clipboard.py`
- `src/openlongpdf/render.py`
- `tests/`
- `README.md`
- `LICENSE`

README requirements:
- Lead with:
  “Turn long foreign-language PDFs into page-aware reading notes.”
  “No cloud lock-in. No extra translation subscription. Use the AI you already pay for.”
- Explain the manual paste-assist workflow clearly:
  1. `openlongpdf prepare book.pdf`
  2. `openlongpdf next workdir --copy --open chatgpt`
  3. paste/send in ChatGPT
  4. copy the translated answer
  5. `openlongpdf paste workdir`
  6. repeat
  7. `openlongpdf assemble workdir`
- Explain that API auto-translation is optional and may incur provider charges.
- Explain that users should only process documents they have the right to read/use.
- Do not include copyrighted translated book samples.
- Include public-domain/synthetic demo.
- Include roadmap:
  - OCR
  - token-aware chunking
  - glossary
  - provider-specific cost estimates
  - provider auth helpers
  - better HTML reader

Tests:
- chunk ordering
- prompt generation
- status detection
- paste target selection
- overwrite protection
- assemble ordering
- HTML escaping/rendering

Success criteria:
A PC user can process a long PDF through the GUI:
- prepare the PDF
- run `openlongpdf gui workdir`
- generate packs
- copy a pack into ChatGPT
- paste the translated response back
- assemble a readable Markdown/HTML note

A user can process a long PDF with a paid API key:
- prepare the PDF
- run `openlongpdf translate ... --model ...`
- confirm with `--yes`
- assemble a readable Markdown/HTML note

A user can still process a long PDF without API keys:
- prepare the PDF
- copy/open the next ChatGPT prompt
- paste the translated result back with one command
- track progress
- assemble a readable Markdown/HTML note
```

# OpenLongPDF Translator

Turn long foreign-language PDFs into page-aware reading notes.

No cloud lock-in. No extra translation subscription. Use the AI you already pay for.

OpenLongPDF Translator is a local-first workflow for reading long foreign-language PDFs with the AI tool you already use. It extracts text from text-layer PDFs, keeps page numbers, splits long documents into translation packs, gives you a local browser GUI for ChatGPT Web/App workflows, captures ChatGPT replies through a visible user-started helper, imports translated chunks, and assembles Markdown and HTML reading notes. A paid OpenAI-compatible API mode is available, but the primary route does not require API keys.

## Install

```bash
pip install -e .
```

For development with `uv`:

```bash
uv run openlongpdf --help
```

## Fastest ChatGPT Route

```bash
openlongpdf run book.pdf --target-language Japanese
```

`run` prepares the PDF, calculates a conservative safe pack size, generates prompt packs, and starts the local GUI.

In the GUI:

1. Open `Browser Assist`.
2. Drag the `OpenLongPDF Assist` bookmarklet to your bookmarks bar.
3. Open ChatGPT in the browser session where you are already logged in.
4. Click the bookmarklet on the ChatGPT page.
5. Choose `Auto-send, capture, import, and assemble remaining packs`.
6. Confirm once at the start of the session.

After that one-time consent, the helper sends each remaining pack, waits for ChatGPT to finish, captures the new assistant response from the visible page, posts it to the local GUI, imports the marked translated chunks, and runs `assemble` when all packs are imported.

This route uses your existing ChatGPT Plus/Pro browser session. OpenLongPDF does not store credentials, cookies, access tokens, or session data.

## Manual And Fallback Workflows

### Local GUI For ChatGPT

```bash
openlongpdf prepare book.pdf --pages-per-chunk 10 --target-language Japanese
openlongpdf gui book_openlongpdf
```

The GUI opens a local browser page where you can:

- generate multi-chunk packs,
- copy a pack to the clipboard,
- install a ChatGPT-side Browser Assist helper,
- send one queued pack, or auto-send/capture/import/assemble remaining queued packs from the ChatGPT page,
- see pack progress: pending, sent, imported, and failed,
- retry a failed pack or reset assist state,
- paste/import responses manually if automatic capture fails,
- assemble the final reading notes manually.

The GUI does not store ChatGPT credentials, cookies, access tokens, or session data. Browser Assist is optional and visible: it runs only after you click its bookmarklet on ChatGPT and confirm the auto session. It may stop if ChatGPT changes its page structure.

### CLI Paste Assist

```bash
openlongpdf prepare book.pdf --pages-per-chunk 10
openlongpdf queue book_openlongpdf --write
openlongpdf pack-plan book_openlongpdf
openlongpdf pack book_openlongpdf --auto
openlongpdf copy-pack book_openlongpdf pack_001 --open chatgpt
# Paste/send the copied pack text in ChatGPT, then save the answer.
openlongpdf import book_openlongpdf book_openlongpdf/output/pack_responses/pack_001_response.md
openlongpdf status book_openlongpdf
openlongpdf assemble book_openlongpdf
```

This creates:

- `source_chunks/`
- `prompts/`
- `translated_chunks/`
- `output/packs/`
- `output/pack_responses/`
- `output/reading_note.md`
- `output/index.html`
- `status.json`
- `manifest.md`

## Paste-Assist Workflow

Pack-based paste assistance is the first-class long-document workflow:

1. `openlongpdf prepare book.pdf`
2. `openlongpdf queue book_openlongpdf --write`
3. `openlongpdf pack-plan book_openlongpdf`
4. `openlongpdf pack book_openlongpdf --auto`
5. Review `output/translation_packs.md` to see every pack file and response save path.
6. `openlongpdf copy-pack book_openlongpdf pack_NNN --open chatgpt`
7. Paste/send the copied pack text in ChatGPT, Claude, Gemini, DeepL, or another translator.
8. Save each translated answer to the suggested `output/pack_responses/pack_NNN_response.md` path.
9. `openlongpdf import book_openlongpdf book_openlongpdf/output/pack_responses/pack_NNN_response.md`
10. Repeat by pack until `openlongpdf status book_openlongpdf` shows no remaining chunks.
11. `openlongpdf assemble book_openlongpdf`

For long documents, inspect the whole queue first:

```bash
openlongpdf queue book_openlongpdf
openlongpdf queue book_openlongpdf --write
openlongpdf queue book_openlongpdf --all
```

`copy-pack ... --open chatgpt` copies a full prompt pack and opens ChatGPT. `next --copy --open chatgpt` does the same for one-chunk fallback. On WSL/Linux, clipboard support prefers PowerShell `Set-Clipboard` before `clip.exe` so non-ASCII text such as Cyrillic, Japanese, and accented Latin characters survives the Windows clipboard boundary. Browser opening tries `cmd.exe /c start`, `wslview`, `xdg-open`, and other safe local openers. If those tools are unavailable, OpenLongPDF prints paths and errors without storing credentials or scraping websites.

`queue` lists every remaining prompt file and the matching translated chunk target. `--write` creates `output/translation_queue.md` as a checklist so a 30+ chunk workload is visible before you start copying prompts.

## Browser Assist

For long PDFs where the safe pack size is small, use the GUI's Browser Assist to avoid copy/paste round trips:

```bash
openlongpdf gui book_openlongpdf
```

In the local GUI:

1. Generate packs.
2. Open `Browser Assist`.
3. Drag the `OpenLongPDF Assist` bookmarklet to your bookmarks bar.
4. Open ChatGPT.
5. Click the bookmarklet on the ChatGPT page.
6. Use `Send next OpenLongPDF pack` for one pack, or `Auto-send, capture, import, and assemble remaining packs` for the full remaining queue.

The helper fetches queued pack text from the local GUI, records the current assistant-message state, fills the ChatGPT composer, clicks send, waits for the response to finish, extracts the newly visible assistant response, and posts it to `POST /assist/import-response` on the local GUI. The GUI saves the raw response under `output/pack_responses/`, imports marked translated chunk blocks into `translated_chunks/`, updates `output/assist_state.json`, and runs `assemble` automatically after all packs are imported.

Automatic capture uses fallback DOM selectors including `[data-message-author-role="assistant"]`, `article`, `.markdown`, and text fallback. This is intentionally a visible browser helper, not ChatGPT scraping in the background. ChatGPT DOM changes can break capture. If capture or import fails, the GUI marks the pack as `failed`, stores the failed response as `output/pack_responses/<pack>_failed_response.md` when available, and shows the failed pack/error so you can retry from the GUI.

`output/assist_state.json` tracks each pack as:

- `pending`
- `sending`
- `sent`
- `imported`
- `failed`

On resume, imported packs are skipped. Failed packs stop auto-run until you use `Retry failed pack` or `Reset assist state` in the GUI.

If a WSL path contains spaces or non-ASCII characters, prefer command variables or tab completion instead of retyping the path. For example:

```bash
WIN_HOME="$(wslpath "$(powershell.exe -NoProfile -Command '[Environment]::GetFolderPath("UserProfile")' | tr -d '\r')")"
PROJECT="$(find "$WIN_HOME/Downloads" -maxdepth 1 -type d -name '*openlongpdf' | head -n 1)"
openlongpdf pack-plan "$PROJECT"
openlongpdf pack "$PROJECT" --auto
```

For one-chunk-at-a-time fallback:

```bash
openlongpdf next book_openlongpdf --copy --open chatgpt
# Paste/send the prompt, copy the translated answer, then:
openlongpdf paste book_openlongpdf
```

## Pack Workflow

For long PDFs, generate fewer larger prompt files:

```bash
openlongpdf pack-plan book_openlongpdf
openlongpdf pack book_openlongpdf --auto
```

`pack-plan` measures the remaining chunks and recommends a conservative pack size for ChatGPT-style web/app output. `pack --auto` uses that recommendation. The defaults keep each pack near or below 40,000 prompt characters and 40,000 source characters, because output truncation is usually the limiting factor. You can still override the result:

```bash
openlongpdf pack book_openlongpdf --chunks-per-pack 3
```

This writes the pack index and prompt files, and the index suggests response save paths:

- `output/translation_packs.md`
- `output/packs/pack_001.md`
- `output/packs/pack_002.md`
- `output/pack_responses/pack_001_response.md` as the suggested save path for the translated answer

Copy a pack to the clipboard with:

```bash
openlongpdf copy-pack book_openlongpdf pack_001 --open chatgpt
```

Do not use `cat output/packs/pack_001.md | clip.exe` on WSL for Cyrillic or other non-ASCII documents; it can produce mojibake. Use `copy-pack`, which uses the Unicode-safe clipboard route when PowerShell is available.

Each pack asks the translator to return marked blocks:

```text
--- BEGIN TRANSLATED CHUNK chunk_001 ---
translated notes
--- END TRANSLATED CHUNK chunk_001 ---
```

After saving a translator response, import all translated chunks in that response at once:

```bash
openlongpdf import book_openlongpdf book_openlongpdf/output/pack_responses/pack_001_response.md
```

`import` refuses to overwrite existing translated chunks unless `--overwrite` is provided. This keeps manual ChatGPT/DeepL-style workflows explicit while avoiding one command per chunk.

## Paid API Automation

For users with API access:

```bash
export OPENAI_API_KEY=...

openlongpdf prepare book.pdf --pages-per-chunk 10 --target-language Japanese
openlongpdf translate book_openlongpdf --model your-paid-model
# Review the planned chunk count and prompt size, then run:
openlongpdf translate book_openlongpdf --model your-paid-model --yes
openlongpdf assemble book_openlongpdf
```

`translate` sends each missing chunk to an OpenAI-compatible `/chat/completions` API, saves every response immediately into `translated_chunks/`, and skips chunks that are already translated. It refuses to call the paid API until `--yes` is provided. By default it reads the API key from `OPENAI_API_KEY`; use `--api-key-env` and `--base-url` for another compatible provider.

ChatGPT Plus/Pro website subscriptions are not API credentials. The primary Browser Assist route uses your logged-in ChatGPT browser session and does not need an API key. The separate `translate` command requires a provider API key and may incur API charges.

## What This Is Not

OpenLongPDF is not a translation model and is not a cloud translation service. It does not implement OCR, a hosted web app, a native app, user accounts, billing, cloud storage, or PDF regeneration. It does not store credentials, cookies, access tokens, or session data.

API-based auto-translation uses provider API keys from environment variables. Browser Assist is a visible user-started helper for an already logged-in ChatGPT tab; it does not authenticate against ChatGPT Web accounts or reuse browser subscriptions as API credentials.

## Copyright And Samples

Only process documents you have the right to read or use. Do not publish translated copyrighted works without permission. Public demos and tests should use public-domain or synthetic documents, not copyrighted translated books.

## Roadmap

- OCR for scanned PDFs
- Token-aware chunking
- Glossary support
- Provider-specific cost estimates
- Better HTML reader

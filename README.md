# OpenLongPDF Translator

Turn long foreign-language PDFs into page-aware reading notes.

No cloud lock-in. No extra translation subscription. Use the AI you already pay for.

OpenLongPDF Translator is a local-first Python CLI workflow. It extracts text from text-layer PDFs, keeps page numbers, splits long documents into translation prompts, helps you paste those prompts into ChatGPT, Claude, Gemini, DeepL, a local LLM, or another tool, and assembles translated chunks into Markdown and HTML reading notes.

## Install

```bash
pip install -e .
```

For development with `uv`:

```bash
uv run openlongpdf --help
```

## MVP Workflow

```bash
openlongpdf prepare book.pdf --pages-per-chunk 10
openlongpdf queue book_openlongpdf --write
openlongpdf pack book_openlongpdf --chunks-per-pack 4
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
3. `openlongpdf pack book_openlongpdf --chunks-per-pack 4`
4. Review `output/translation_packs.md` to see every pack file and response save path.
5. `openlongpdf copy-pack book_openlongpdf pack_NNN --open chatgpt`
6. Paste/send the copied pack text in ChatGPT, Claude, Gemini, DeepL, or another translator.
7. Save each translated answer to the suggested `output/pack_responses/pack_NNN_response.md` path.
8. `openlongpdf import book_openlongpdf book_openlongpdf/output/pack_responses/pack_NNN_response.md`
9. Repeat by pack until `openlongpdf status book_openlongpdf` shows no remaining chunks.
10. `openlongpdf assemble book_openlongpdf`

For long documents, inspect the whole queue first:

```bash
openlongpdf queue book_openlongpdf
openlongpdf queue book_openlongpdf --write
openlongpdf queue book_openlongpdf --all
```

`copy-pack ... --open chatgpt` copies a full prompt pack and opens ChatGPT. `next --copy --open chatgpt` does the same for one-chunk fallback. On WSL/Linux, clipboard support prefers PowerShell `Set-Clipboard` before `clip.exe` so non-ASCII text such as Cyrillic, Japanese, and accented Latin characters survives the Windows clipboard boundary. Browser opening tries `cmd.exe /c start`, `wslview`, `xdg-open`, and other safe local openers. If those tools are unavailable, OpenLongPDF prints paths and errors without storing credentials or scraping websites.

`queue` lists every remaining prompt file and the matching translated chunk target. `--write` creates `output/translation_queue.md` as a checklist so a 30+ chunk workload is visible before you start copying prompts.

For one-chunk-at-a-time fallback:

```bash
openlongpdf next book_openlongpdf --copy --open chatgpt
# Paste/send the prompt, copy the translated answer, then:
openlongpdf paste book_openlongpdf
```

## Pack Workflow

For long PDFs, generate fewer larger prompt files:

```bash
openlongpdf pack book_openlongpdf --chunks-per-pack 4
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

## What This Is Not

OpenLongPDF is not a translation model and is not a cloud translation service. It does not implement OCR, a GUI, a web app, a native app, user accounts, billing, cloud storage, PDF regeneration, or ChatGPT scraping. It does not store credentials, cookies, access tokens, or session data.

API-based auto-translation can be added later through official APIs, but the MVP is designed to work without API keys.

## Copyright And Samples

Only process documents you have the right to read or use. Do not publish translated copyrighted works without permission. Public demos and tests should use public-domain or synthetic documents, not copyrighted translated books.

## Roadmap

- OCR for scanned PDFs
- Token-aware chunking
- Glossary support
- Official API auto-translation
- Better HTML reader
- Local LLM integration

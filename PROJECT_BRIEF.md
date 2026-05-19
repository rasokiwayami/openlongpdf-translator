# OpenLongPDF Translator Project Brief

## Core Idea

OpenLongPDF Translator is an OSS tool for people who need to read long foreign-language PDFs without paying for another document-translation subscription.

It is not a translation model. It is a local-first workflow tool that:

- extracts text from long PDFs page by page,
- preserves page numbers,
- splits the document into manageable translation chunks,
- generates prompts for ChatGPT, Claude, Gemini, DeepL, local LLMs, or API-based translation,
- helps the user paste translated chunks back,
- assembles the result into page-aware Markdown and HTML reading notes.

## Why This Should Exist

Many students, researchers, and independent readers already pay for ChatGPT, Claude, Gemini, or another AI tool. Yet when they need to read a 300-page foreign-language PDF, they often hit file limits, document translation paywalls, or awkward workflows such as taking screenshots page by page.

This project exists to reduce that friction.

The value is not "better translation than DeepL." The value is:

- no cloud lock-in,
- no extra translation subscription required,
- readable long-document workflow,
- page-aware output,
- local-first processing,
- user choice of translation engine,
- reusable reading notes rather than opaque translated files.

## Positioning

Use strong OSS language, but do not frame the project as hostile to a specific company.

Good framing:

> Stop paying extra subscriptions to read documents you already have.

> Use the AI you already pay for.

> Turn long foreign-language PDFs into page-aware reading notes.

Avoid:

> This project exists to attack DeepL.

> This tool is for pirating books.

> This bypasses paid services.

The public message should be about knowledge access, local-first tools, user control, and reducing unnecessary translation rent.

## Target User

Primary:

- students reading long foreign-language PDFs,
- humanities students reading non-English sources,
- graduate students and independent researchers,
- technical readers who want long PDFs converted into Markdown/HTML notes,
- people who already pay for ChatGPT/Claude/Gemini but do not want another document translation subscription.

Secondary:

- developers who want a reusable PDF-to-translation-chunk workflow,
- local LLM users,
- people who want to compare outputs from multiple translation engines.

## MVP Scope

Build a Python CLI first.

Required commands:

- `openlongpdf prepare <pdf>`
- `openlongpdf status <project_dir>`
- `openlongpdf next <project_dir>`
- `openlongpdf queue <project_dir>`
- `openlongpdf pack <project_dir>`
- `openlongpdf copy-pack <project_dir> <pack>`
- `openlongpdf paste <project_dir>`
- `openlongpdf import <project_dir> <response_file>`
- `openlongpdf assemble <project_dir>`

Required workflow:

1. User prepares a PDF.
2. Tool extracts page-aware text.
3. Tool splits it into translation chunks.
4. Tool generates prompt files.
5. Tool shows a full translation queue with every prompt file and save target.
6. Tool can group remaining chunks into larger prompt packs.
7. Tool copies prompt packs through a Unicode-safe clipboard route, especially on WSL/Windows.
8. User pastes prompt packs into ChatGPT, Claude, Gemini, DeepL, or another AI.
9. User saves the marked translated answer.
10. Tool imports every translated chunk from that marked answer.
11. Tool still supports one-chunk-at-a-time `next` and `paste` fallback.
12. Tool tracks progress.
13. Tool assembles Markdown and HTML reading notes.

## MVP Non-Goals

Do not implement these in the first version:

- OCR,
- GUI,
- native app,
- web app,
- user accounts,
- billing,
- cloud storage,
- PDF regeneration,
- layout-preserving translated PDF output,
- fully automated ChatGPT scraping,
- credential or cookie storage,
- copyrighted translated sample books.

## Browser / ChatGPT Assistance Boundary

Manual paste assistance is part of the MVP.

Good:

- copy next prompt to clipboard,
- open ChatGPT/Claude/Gemini URL,
- show the target translated chunk file,
- read clipboard and save it as the next translated chunk,
- refuse accidental overwrite.

Avoid in MVP:

- automatically extracting ChatGPT output,
- bypassing rate limits or UI restrictions,
- storing account credentials,
- automating bulk ChatGPT submissions in the background.

API-based full automation can be added later through official APIs.

## Auth And Full-Automation Direction

The project should eventually support full automatic translation of all chunks, but that should be implemented through official provider APIs, not through unattended ChatGPT website scraping.

Good full-automation path:

- `openlongpdf auth openai`
- `openlongpdf auth deepl`
- `openlongpdf translate <project_dir> --provider openai --model gpt-5.4`
- `openlongpdf translate <project_dir> --provider deepl`

The auth flow should run during onboarding or first use, not silently:

1. Detect whether the selected provider is configured.
2. If not configured, ask the user to choose:
   - environment variable only,
   - local user config,
   - OS keyring if available.
3. Never store ChatGPT account cookies, browser sessions, passwords, or access tokens.
4. Explain that ChatGPT Plus/Pro subscription access is not the same thing as API access.
5. For true unattended batch translation, require official API credentials.

ChatGPT website assistance can still be useful, but it should remain visible and user-controlled:

- copy/open the next prompt,
- optionally focus a browser window,
- let the user press send,
- let the user review/copy the result,
- save the result with `openlongpdf paste`.

Do not implement background bulk submission to ChatGPT Web, output scraping, rate-limit bypassing, or any flow that treats ChatGPT Web as an unofficial API.

## Copyright And Safety Stance

The tool should process documents supplied by the user. It should not ship copyrighted PDFs or translated copyrighted books.

README should say:

- only process documents you have the right to read or use,
- do not publish translated copyrighted works without permission,
- sample inputs and demos use public-domain or synthetic documents,
- this project is a reading-assistance workflow, not a content redistribution platform.

## First Success Criteria

A user can run:

```powershell
openlongpdf prepare book.pdf --pages-per-chunk 10
openlongpdf pack .\book_openlongpdf --chunks-per-pack 4
openlongpdf copy-pack .\book_openlongpdf pack_001 --open chatgpt
openlongpdf import .\book_openlongpdf .\book_openlongpdf\output\pack_responses\pack_001_response.md
openlongpdf status .\book_openlongpdf
openlongpdf assemble .\book_openlongpdf
```

and get:

- `output/reading_note.md`
- `output/index.html`

with page numbers and chunk order preserved.

## Star-Worthy Demo

The first public demo should use a public-domain or synthetic PDF.

Show:

- long PDF input,
- number of pages,
- generated chunks,
- next prompt workflow,
- status output,
- final HTML reading note screenshot.

The demo should make the user think:

> I can use this today with the AI subscription I already have.

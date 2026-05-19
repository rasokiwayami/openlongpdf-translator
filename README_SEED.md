# OpenLongPDF Translator

Turn long foreign-language PDFs into page-aware reading notes.

No cloud lock-in. No extra translation subscription. Use the ChatGPT/Claude/Gemini/DeepL account you already have, with an optional paid API mode.

## What This Is

OpenLongPDF Translator is an OSS CLI workflow for long PDF reading.

It extracts text from PDFs, keeps page numbers, splits long documents into translation prompts, gives you a local browser GUI for copying packs into ChatGPT, and assembles translated chunks into Markdown and HTML reading notes.

## What This Is Not

This is not a translation model.

This is not a cloud translation service.

This is not a tool for publishing translated copyrighted books.

## MVP Workflow

```powershell
openlongpdf prepare book.pdf --pages-per-chunk 10
openlongpdf gui .\book_openlongpdf
```

CLI fallback:

```powershell
openlongpdf queue .\book_openlongpdf --write
openlongpdf pack .\book_openlongpdf --chunks-per-pack 4
openlongpdf copy-pack .\book_openlongpdf pack_001 --open chatgpt
# Paste/send the copied pack text in ChatGPT, then save the answer.
openlongpdf import .\book_openlongpdf .\book_openlongpdf\output\pack_responses\pack_001_response.md
openlongpdf status .\book_openlongpdf
openlongpdf assemble .\book_openlongpdf
```

For long documents, the GUI can generate packs, copy each pack, import translated responses, and assemble reading notes. CLI users can still run `queue --write`, `pack`, and `copy-pack`.

## Why

People should not have to screenshot 300-page PDFs just to read them.

Many readers already pay for a capable AI assistant. This tool helps them use that existing access to read long documents without another opaque document translation workflow.

Your PDFs. Your AI. Your reading notes.

## Automation Direction

Optional automatic chunk translation uses official/OpenAI-compatible provider APIs:

```bash
export OPENAI_API_KEY=...
openlongpdf translate book_openlongpdf --model your-paid-model --yes
```

ChatGPT Plus/Pro website access is not the same as API access. This project should not store ChatGPT browser cookies or scrape ChatGPT output. Browser assistance can open ChatGPT and copy prompts, but unattended batch translation should use official APIs.

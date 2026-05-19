# OpenLongPDF Translator

Turn long foreign-language PDFs into page-aware reading notes.

No cloud lock-in. No extra translation subscription. Use ChatGPT, Claude, Gemini, DeepL, local LLMs, or your own API keys.

## What This Is

OpenLongPDF Translator is an OSS CLI workflow for long PDF reading.

It extracts text from PDFs, keeps page numbers, splits long documents into translation prompts, helps you paste those prompts into the AI tool you already use, and assembles translated chunks into Markdown and HTML reading notes.

## What This Is Not

This is not a translation model.

This is not a cloud translation service.

This is not a tool for publishing translated copyrighted books.

## MVP Workflow

```powershell
openlongpdf prepare book.pdf --pages-per-chunk 10
openlongpdf queue .\book_openlongpdf --write
openlongpdf pack .\book_openlongpdf --chunks-per-pack 4
openlongpdf copy-pack .\book_openlongpdf pack_001 --open chatgpt
# Paste/send the copied pack text in ChatGPT, then save the answer.
openlongpdf import .\book_openlongpdf .\book_openlongpdf\output\pack_responses\pack_001_response.md
openlongpdf status .\book_openlongpdf
openlongpdf assemble .\book_openlongpdf
```

For long documents, `queue --write` creates `output/translation_queue.md`, `pack` creates larger prompt files under `output/packs/`, and `copy-pack` copies a pack through the Unicode-safe clipboard route on WSL/Windows.

## Why

People should not have to screenshot 300-page PDFs just to read them.

Many readers already pay for an AI assistant. This tool helps them use that existing subscription or their own API keys to read long documents without another opaque document translation workflow.

Your PDFs. Your AI. Your reading notes.

## Automation Direction

The manual paste workflow is the first version because it works without API keys.

Full automatic chunk translation should be added through official provider APIs:

```bash
openlongpdf auth openai
openlongpdf translate book_openlongpdf --provider openai --model gpt-5.4
```

ChatGPT Plus/Pro website access is not the same as API access. This project should not store ChatGPT browser cookies or scrape ChatGPT output. Browser assistance can open ChatGPT and copy prompts, but unattended batch translation should use official APIs.

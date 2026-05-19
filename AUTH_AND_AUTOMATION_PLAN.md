# Auth And Automation Plan

## Goal

Add a path for users who want OpenLongPDF to translate all chunks automatically.

The safe implementation path is official provider APIs. ChatGPT Web assistance remains a human-in-the-loop workflow.

## Why Not Full ChatGPT Web Automation

ChatGPT Web is a user interface, not an API. Treating it as an unattended batch translation backend creates fragile behavior and account-policy risk:

- login state is private browser state,
- UI changes can break automation,
- output scraping is not a stable interface,
- rate limits and usage limits are not an integration contract,
- credentials/cookies should not be stored by this CLI.

Therefore:

- Do not implement background bulk submission to ChatGPT Web.
- Do not scrape ChatGPT output.
- Do not store ChatGPT cookies, sessions, passwords, or browser tokens.

## Supported Automation Path

Use official APIs.

Current command:

```bash
export OPENAI_API_KEY=...
openlongpdf translate book_openlongpdf --model your-paid-model
openlongpdf translate book_openlongpdf --model your-paid-model --yes
```

Provider-specific auth helpers can be added later, but the first supported path is environment variables plus an OpenAI-compatible chat completions endpoint.

## Auth Flow

Initial implementation should prefer environment variables:

- `OPENAI_API_KEY`
- `DEEPL_API_KEY`

Then add explicit user config if needed:

```bash
openlongpdf auth openai --set-key
openlongpdf auth openai --from-env
openlongpdf auth list
openlongpdf auth clear openai
```

Storage options, in order of preference:

1. Environment variables.
2. OS keyring when available.
3. Local config only if explicitly requested, with clear warning.

Never silently write secrets.

## Translate Command Behavior

`openlongpdf translate` should:

1. Load project status.
2. Find untranslated chunks.
3. Estimate cost when possible.
4. Ask for confirmation unless `--yes` is passed.
5. Translate chunks one by one.
6. Save each result immediately to `translated_chunks/`.
7. Update status after each chunk.
8. Resume safely after interruption.
9. Refuse to overwrite translated chunks unless `--overwrite` is passed.
10. Produce a final summary.

## Browser Assist Boundary

Allowed:

- copy the next prompt,
- open ChatGPT/Claude/Gemini/DeepL in the browser,
- show the save target,
- let the user copy the result,
- save clipboard content with `openlongpdf paste`.

Not allowed:

- automatically press send repeatedly,
- extract ChatGPT output from the DOM,
- bypass login, CAPTCHA, usage limits, or rate limits,
- store browser credentials.

## MVP Relationship

The current MVP should remain useful without API keys.

The paid API `translate` path now sits beside the manual workflow:

- `prepare`
- `status`
- `next`
- `queue`
- `pack`
- `copy-pack`
- `paste`
- `import`
- `assemble`

Manual paste remains available for users without API keys.

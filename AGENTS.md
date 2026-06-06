# Agent Guidelines

This repository is a local-first PDF extraction and translation-note workflow.
Treat Python source, tests, `pyproject.toml`, and `PROJECT_PROFILE.yaml` as the
operating truth. README prose is secondary when it lags implementation.

## Global Routing

For non-trivial implementation, route through Jinsei / Global Coding Department:

```bash
cd /Users/sora/dev/jinsei
python3 scripts/dispatch_codex_session.py --queue-request --project "OpenLongPDF Translator" --repo /Users/sora/dev/openlongpdf-translator --operation-id <operation_id> --goal "<bounded goal>" --authority-band A2
python3 scripts/dispatch_codex_session.py --from-queue --limit 3
python3 scripts/dispatch_codex_session.py --check-push-review --project "OpenLongPDF Translator" --operation-id <operation_id>
```

Use Planning Worker, Implementation Worker, and Review Controller separation for
multi-file changes, PDF parsing behavior, clipboard/GUI behavior, external API
translation, public/push readiness, or workflow contract changes.

## Engineering Rules

- Prefer existing Python modules and tests.
- Keep PDF processing local-first and deterministic where possible.
- Do not add external services to the default path without explicit approval.
- Do not commit generated PDFs, extracted private document text, translation
  outputs, or raw local workspaces.

## Safety

Do not read, print, commit, or copy `.env*`, API keys, private PDFs, extracted
private document bodies, clipboard-sensitive content, raw logs, or generated
runtime workspaces unless the user explicitly scopes that local file for the
current task.

## Verification

Use the relevant subset:

```bash
uv run --extra dev python -m pytest
git diff --check
```

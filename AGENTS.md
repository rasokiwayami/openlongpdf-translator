# Agent Guidelines

This repository is a local-first PDF extraction and translation-note workflow.
Treat Python source, tests, `pyproject.toml`, and `PROJECT_PROFILE.yaml` as the
operating truth. README prose is secondary when it lags implementation.

## Development Route

For non-trivial implementation, use the parent-owned route:
Plan -> Work -> independent Sol max Review. The central instructions are
`/Users/sora/dev/jinsei/CODEX_GLOBAL_AGENTS.md`, and the deterministic task,
authority, evidence, and Git boundary is `/Users/sora/dev/jinsei/bin/jinsei`.
The Codex parent owns model launch; the current TaskIntent, exact worktree
scope, and fresh verification/review evidence must bind to the current HEAD.
Do not infer launch commands from this repository.

## Development Autonomy

Development GitHub operations are L5 under Jinsei's
`GITHUB_DEVOPS_AUTONOMY_POLICY.md` after this repo's verification and fresh
independent Sol max review evidence bound to the current HEAD pass. This
includes branch work, local commits, pushes to an existing approved remote, PR
creation/update, and issue operations.

Public deployment, repository visibility changes, billing or paid services,
secret mutation, production data mutation, public claims, and publication remain
gated.

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

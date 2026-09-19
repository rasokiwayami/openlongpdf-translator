# Agent Guidelines

This repository is a local-first PDF extraction and translation-note workflow.
Treat Python source, tests, `pyproject.toml`, and `PROJECT_PROFILE.yaml` as the
operating truth. README prose is secondary when it lags implementation.

## Development Route

For non-trivial implementation, use the parent-owned route:
Plan -> Work -> Review. The current central contract and linked policies own
the route, model and effort selection, review, task evidence, and Git side
effects:

- `/Users/sora/dev/jinsei/CODEX_GLOBAL_AGENTS.md`
- `/Users/sora/dev/jinsei/docs/policies/DEVELOPMENT_MODEL_ROUTE_POLICY.md`
- `/Users/sora/dev/jinsei/docs/policies/DEVELOPMENT_PROTOCOL.md`
- `/Users/sora/dev/jinsei/docs/policies/MANAGED_REPOSITORY_INHERITANCE.md`

The central harness boundary is `/Users/sora/dev/jinsei/bin/jinsei`; do not
infer launch commands from this repository. The `project.authority` block in
`PROJECT_PROFILE.yaml` is a target-local narrowing filter. It does not grant
authority or replace central task, halt, identity, or review checks.

## Repository Scope

This repository is a specialized Jinsei-managed PDF tool. It owns the PDF
source code and private local runtime artifacts. For cross-repository work,
read only directly affected contracts and consumers. No current external
runtime caller is verified for this component; do not invent one.

## Engineering Rules

- Prefer existing Python modules and tests.
- Keep PDF processing local-first and deterministic where possible.
- External API calls, including optional paths, require exact approval in the
  current task.
- Permission to read a local file does not authorize sending private PDFs or
  extracted document bodies to any external service.
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

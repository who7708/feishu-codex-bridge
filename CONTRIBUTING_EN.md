# Contributing

[中文](CONTRIBUTING.md)

Thanks for helping improve Feishu Codex Bridge.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest
python3 -m pytest -q
```

Tests should run without real Feishu credentials or real Codex network calls.

## Pull Requests

- Keep changes scoped.
- Add or update tests for behavior changes.
- Do not commit `.env`, tokens, app secrets, session files, logs, or local caches.
- Prefer preserving the current module boundaries: runner, commands, session store, Feishu client, and main event flow.

## Safety

Changes touching permission modes, process execution, image/file handling, or Feishu event routing should include tests and README updates when user-facing behavior changes.

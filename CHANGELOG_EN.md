# Changelog

[中文](CHANGELOG.md)

## 0.1.0 - 2026-04-24

First open-source Codex bridge release, adapted from the MIT-licensed `feishu-claudecode-bridge` project with the original copyright notice preserved.

### Added

- Trigger local Codex CLI from Feishu/Lark private chats, group chats, and topics.
- Full message flow from Feishu/Lark events to Codex execution, streaming card updates, and final replies.
- Support for `codex exec --json` and `codex exec resume --json`.
- Codex JSONL event parsing for text deltas, tool calls, and command progress.
- Final response loading from `--output-last-message`.
- Image message download and forwarding to Codex CLI through `--image`.
- Session discovery from `~/.codex/sessions/**/*.jsonl` and `session_index.jsonl`.
- Per-chat/topic context for workspace, model, mode, and Codex session state.
- Commands including `/new`, `/resume`, `/model`, `/mode`, `/status`, `/cd`, `/ws`, `/stop`, `/mcp`, `/skills`, `/plugins`, and `/usage`.
- `/stop` support for terminating a running Codex process.
- Feishu/Lark permission import config at `config/feishu_permissions.json`.
- Linux + systemd deployment docs for 24/7 cloud-server operation.

### Security And Defaults

- Default permission mode is `plan`, so the open-source default does not start in full auto-execution mode.
- Supports switching between `plan`, `workspace`, `danger`, and related permission modes.
- README and deployment docs explicitly warn about `danger` / full-permission auto mode.
- `.env.example` contains no real credentials.

### Documentation

- Added Chinese default README and English `README_EN.md`.
- Added product plan docs: `docs/PRODUCT_PLAN.md` and `docs/PRODUCT_PLAN_EN.md`.
- Added Linux deployment docs: `docs/DEPLOY_LINUX.md` and `docs/DEPLOY_LINUX_EN.md`.
- Added bilingual contributing guide, security policy, troubleshooting guide, and changelog.

### Tests

- Added a pytest-based test suite.
- Covered Codex runner, session store, command handling, and Feishu/Lark message flow.
- Tests run without real Feishu/Lark service access or real Codex network calls.

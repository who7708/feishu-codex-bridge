# Feishu Codex Bridge Product Plan

[中文](PRODUCT_PLAN.md)

## Product Goal

Feishu Codex Bridge lets a user operate the local Codex CLI from Feishu/Lark. The bridge runs on the user's own machine or server, receives Feishu messages through `lark-cli` WebSocket events, invokes the local `codex` executable, and streams progress back into Feishu cards.

The product is for engineers who want to inspect, modify, review, or debug local projects from Feishu without opening a terminal. It reuses the user's existing Codex login and local filesystem access; it does not provide a cloud-hosted Codex runtime.

## Target Users And Scenarios

- A developer sends a private Feishu message to ask Codex to inspect or modify a project.
- A project group mentions the bot, and Codex works in that group's bound workspace.
- A topic thread maps to its own Codex session so discussion context stays isolated.
- A user sends a screenshot or image, and Codex receives it as an image input.
- A user stops a long-running task from Feishu with `/stop`.
- A user resumes or switches sessions, models, permission modes, and workspaces from Feishu.

## In Scope

- Feishu private chat, group chat, and topic-thread handling.
- Streaming card output for Codex text and tool progress.
- Image download from Feishu and forwarding to Codex with `--image`.
- Codex session persistence and `/resume` support using `~/.codex/sessions` and `~/.codex/session_index.jsonl`.
- Workspace management with `/cd`, `/ls`, `/workspace`, and `/ws`.
- Run control with `/stop` and automatic interruption by a newer message in the same chat.
- Codex metadata commands: `/model`, `/mode`, `/mcp`, `/skills`, `/plugins`, and `/usage`.
- Document comment reply support through the same Codex runner.
- Linux systemd deployment examples and operational docs for 24/7 cloud-server operation.

## Out Of Scope

- Web administration UI.
- Multi-user approval or RBAC system.
- Cloud-hosted Codex execution.
- Cross-machine session synchronization.
- Modifying or migrating the existing Claude bridge.
- Direct Feishu file editing beyond reading message images and replying to comments.

## Permissions And Safety Boundaries

For public releases, the default mode is `plan`. Private deployments can opt into `workspace` or `danger`. `danger` invokes Codex with `--dangerously-bypass-approvals-and-sandbox`, which allows Feishu messages to trigger local file changes and commands without interactive approval.

The bridge must make this risk explicit in README and `/mode` output. Safer modes must remain available:

- `plan`: read-only planning with no file writes.
- `workspace`: writable workspace mode using Codex full-auto behavior.
- `danger`: full automatic execution without approvals or sandboxing.

All modes run on the user's machine with the user's Codex credentials. The bridge does not add its own remote authentication layer beyond the Feishu app credentials.

## Feishu Interaction Rules

- Private messages always address the bot.
- Group messages require an explicit bot mention; non-mentioned messages are ignored by Feishu event configuration or local mention stripping.
- Topic groups use `thread_id` or `root_id` as part of the chat key so sessions do not leak across topics.
- The first bot response is a loading card; subsequent output patches the same card.
- If the final card update fails, the bridge falls back to a normal Feishu reply.
- Button replies are treated as follow-up messages in the same chat/session.

## Codex CLI Mapping

- New run: `codex exec --json -C <cwd> -`.
- Resumed run: `codex exec resume --json <session_id> -`.
- Final response capture: `--output-last-message <tempfile>`.
- Model selection: `-m <model>`.
- Image input: one `--image <path>` per downloaded image.
- Planning mode: `--sandbox read-only`.
- Workspace mode: `--full-auto`.
- Danger mode: `--dangerously-bypass-approvals-and-sandbox`.

The runner reads JSONL from stdout for streaming progress and uses the final-message file as the authoritative final response when present.

## Error Handling

- Non-zero Codex exit with partial output returns the partial output and appends an error note.
- Non-zero Codex exit without output raises a clear error including stderr.
- Permission failures touching `~/.codex` are rewritten into a user-facing hint explaining that the bridge process needs access to Codex session files.
- Idle output timeout terminates the Codex process and reports a timeout.
- `/stop` terminates the current process gracefully, then kills it after a short grace period.

## Acceptance Criteria

- `pytest` passes in `feishu-codex-bridge` without real Feishu or real Codex network calls.
- `docs/PRODUCT_PLAN.md` answers what the product does, what it does not do, and how success is verified.
- `README.md` documents the `danger` full-permission risk and safer mode choices.
- The existing `feishu-claudecode-bridge` directory is not modified.
- Tests cover runner command construction, JSONL parsing, session scanning, command handling, and the main Feishu-to-Codex message flow.

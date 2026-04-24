# Security Policy

[中文](SECURITY.md)

## Reporting Security Issues

Please do not open public issues for secrets, remote execution vulnerabilities, or permission bypasses. Report privately through the repository owner's preferred contact channel.

## Operational Risks

This bridge can execute Codex on the machine where it runs. In `danger` mode, Feishu messages can trigger local shell commands and file edits without interactive approval.

Use these defaults for public or shared deployments:

```env
DEFAULT_MODE=plan
```

Recommended precautions:

- Use a dedicated Feishu/Lark app for this bridge.
- Do not invite the bot to untrusted groups.
- Run with a dedicated OS user where possible.
- Keep `.env`, `~/.codex`, and `~/.lark-cli` private.
- Review logs before switching to `/mode workspace` or `/mode danger`.

## Secret Handling

Never commit:

- `.env`
- Feishu/Lark app secrets
- Codex auth files
- `~/.codex/sessions`
- `~/.lark-cli/config.json`
- production logs

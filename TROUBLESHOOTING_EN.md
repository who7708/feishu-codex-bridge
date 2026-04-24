# Troubleshooting

[中文](TROUBLESHOOTING.md)

## The Bot Is Connected But Does Not Reply

First check whether the service logs contain `[收到消息]`:

```bash
journalctl -u feishu-codex-bridge -f
```

- No: Feishu/Lark events are probably not reaching the bridge.
- Yes: the issue is probably Codex, card updates, or permission mode handling.

### Check Feishu/Lark App Configuration

`main.py` sends messages using `FEISHU_APP_ID` / `FEISHU_APP_SECRET` from `.env`, while message receiving goes through `lark-cli event +subscribe`. If the global `lark-cli` config points to a different app, the bridge may appear connected but never receive events for this bot.

```bash
cd /opt/feishu-codex-bridge
lark-cli config show | grep appId
grep FEISHU_APP_ID .env
```

The two App IDs must match. If they do not, reinitialize `lark-cli`:

```bash
set -a
source .env
set +a

printf '%s' "$FEISHU_APP_SECRET" |
  lark-cli config init --app-id "$FEISHU_APP_ID" --app-secret-stdin --brand feishu
```

Also verify:

- The bot capability is enabled in the developer console.
- Permissions from [config/feishu_permissions.json](config/feishu_permissions.json) have been imported.
- In "Events and callbacks", both "Events" and "Callbacks" use long connection mode.
- The event `im.message.receive_v1` is subscribed.
- The callback `card.action.trigger` is enabled.
- The app has been published and approved by an admin.

## Codex Fails

Make sure the bridge service user can use Codex CLI directly:

```bash
codex --version
codex exec --skip-git-repo-check --json "hello"
```

If the logs mention lack of access to `~/.codex`, make sure the bridge runs as the same OS user that logged into Codex. For systemd deployments, pay special attention to `User`, `HOME`, and `PATH`.

```bash
systemctl cat feishu-codex-bridge
```

## The Service Does Not Start Or Keeps Restarting

Check status and logs:

```bash
systemctl status feishu-codex-bridge --no-pager
journalctl -u feishu-codex-bridge -n 120 --no-pager
```

Common causes:

- `.env` is missing `FEISHU_APP_ID` or `FEISHU_APP_SECRET`.
- `lark-cli` is configured for a different app.
- `codex` or `lark-cli` is not in systemd's `PATH`.
- `WorkingDirectory` or `ExecStart` in the service file is incorrect.

## Card Buttons Do Not Respond

Card buttons rely on the `card.action.trigger` callback.

Check:

- "Callbacks" use long connection mode in the developer console.
- The callback `card.action.trigger` is enabled.
- The logs contain `[卡片回调]`.

If there are no callback logs, this is usually a Feishu/Lark app callback configuration issue, not a Codex execution issue.

## Images Cannot Be Analyzed

Image messages are downloaded to a local temporary path first, then passed to Codex CLI with `--image`.

Check:

- Permissions from [config/feishu_permissions.json](config/feishu_permissions.json) have been imported.
- The app has been published and permissions have taken effect.
- The logs contain `下载图片失败`.

## Full-Permission Mode Is Too Dangerous

`DEFAULT_MODE=danger` calls `codex exec --dangerously-bypass-approvals-and-sandbox`.

Use it only for a trusted personal bot. Public or shared deployments should keep:

```bash
DEFAULT_MODE=plan
```

Or switch from Feishu:

```bash
/mode plan
/mode workspace
```

## Common systemd Commands

```bash
systemctl status feishu-codex-bridge --no-pager
journalctl -u feishu-codex-bridge -f

systemctl restart feishu-codex-bridge
systemctl stop feishu-codex-bridge
systemctl start feishu-codex-bridge
```

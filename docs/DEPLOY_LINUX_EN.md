# Linux Deployment

[中文](DEPLOY_LINUX.md)

This guide deploys `feishu-codex-bridge` as a `systemd` service. A Linux cloud server is the recommended target because it keeps the bot online 24/7 without depending on a personal laptop being awake.

## 1. Install System Packages

For Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nodejs npm
```

For RHEL/OpenCloudOS/CentOS-style systems:

```bash
sudo dnf install -y python3 python3-pip nodejs npm
```

## 2. Install CLIs

The systemd service user is expected to have Codex CLI installed and working. For first-time installation or login troubleshooting, see the official OpenAI guide: [OpenAI Codex CLI getting started](https://help.openai.com/en/articles/11096431-openai-codex-ligetting-started).

```bash
sudo npm install -g @openai/codex @larksuite/cli

codex --version
lark-cli --version
```

Make sure Codex works on the server:

```bash
codex exec --skip-git-repo-check --json "hello"
```

## 3. Configure Feishu/Lark

1. Create a custom Feishu/Lark app in the developer console.
2. Add the bot capability.
3. Import the permissions from [../config/feishu_permissions.json](../config/feishu_permissions.json).
4. In "Events and callbacks", set both "Events" and "Callbacks" to long connection mode.
5. Subscribe to the event: `im.message.receive_v1`.
6. Enable the callback: `card.action.trigger`, used for card buttons.
7. Save the App ID and App Secret for `.env`.

## 4. Install The Bridge

```bash
sudo mkdir -p /opt/feishu-codex-bridge
sudo chown "$USER":"$USER" /opt/feishu-codex-bridge

git clone https://github.com/your-org/feishu-codex-bridge.git /opt/feishu-codex-bridge
cd /opt/feishu-codex-bridge

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 5. Configure `.env` And lark-cli

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env`:

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
DEFAULT_MODEL=gpt-5.5
DEFAULT_CWD=/opt/feishu-codex-bridge/workspace
DEFAULT_MODE=plan
```

Initialize `lark-cli`:

```bash
set -a
source .env
set +a

printf '%s' "$FEISHU_APP_SECRET" |
  lark-cli config init --app-id "$FEISHU_APP_ID" --app-secret-stdin --brand feishu

lark-cli config show
```

## 6. Create A systemd Service

Copy the sample:

```bash
sudo cp deploy/feishu-codex.service /etc/systemd/system/feishu-codex-bridge.service
```

Edit the service if you changed the install path or service user.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now feishu-codex-bridge
sudo systemctl status feishu-codex-bridge --no-pager
```

Logs:

```bash
journalctl -u feishu-codex-bridge -f
```

You should see:

```text
[lark-cli] ✅ 事件订阅已连接
```

## 7. Smoke Test

In Feishu, send:

```text
/status
```

Then:

```text
hello, reply with one sentence
```

Keep `DEFAULT_MODE=plan` until the message/card flow is confirmed.

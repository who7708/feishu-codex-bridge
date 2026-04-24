# Linux 部署

[English](DEPLOY_LINUX_EN.md)

这份文档说明如何把 `feishu-codex-bridge` 部署成 `systemd` 服务。推荐部署到 Linux 云服务器，这样机器人不依赖个人电脑开机状态，可以 7x24 小时在线待命。

## 1. 安装系统依赖

Debian/Ubuntu：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nodejs npm
```

RHEL/OpenCloudOS/CentOS 系：

```bash
sudo dnf install -y python3 python3-pip nodejs npm
```

## 2. 安装 CLI

项目默认 systemd 运行用户已经安装 Codex CLI，并且该用户可以正常使用 Codex。首次安装或排查登录问题，请参考 OpenAI 官方文档：[OpenAI Codex CLI getting started](https://help.openai.com/en/articles/11096431-openai-codex-ligetting-started)。

```bash
sudo npm install -g @openai/codex @larksuite/cli

codex --version
lark-cli --version
```

确认 Codex 在服务器上可用：

```bash
codex exec --skip-git-repo-check --json "hello"
```

## 3. 配置飞书

1. 在飞书开放平台创建企业自建应用。
2. 添加机器人能力。
3. 导入 [../config/feishu_permissions.json](../config/feishu_permissions.json) 文件中的权限。
4. 在「事件与回调」中，将「事件」和「回调」都设置为长连接模式。
5. 订阅事件：`im.message.receive_v1`。
6. 启用回调：`card.action.trigger`，用于处理卡片按钮。
7. 保存 App ID 和 App Secret，稍后写入 `.env`。

## 4. 安装 bridge

```bash
sudo mkdir -p /opt/feishu-codex-bridge
sudo chown "$USER":"$USER" /opt/feishu-codex-bridge

git clone https://github.com/your-org/feishu-codex-bridge.git /opt/feishu-codex-bridge
cd /opt/feishu-codex-bridge

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 5. 配置 `.env` 和 lark-cli

```bash
cp .env.example .env
chmod 600 .env
```

编辑 `.env`：

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
DEFAULT_MODEL=gpt-5.5
DEFAULT_CWD=/opt/feishu-codex-bridge/workspace
DEFAULT_MODE=plan
```

初始化 `lark-cli`：

```bash
set -a
source .env
set +a

printf '%s' "$FEISHU_APP_SECRET" |
  lark-cli config init --app-id "$FEISHU_APP_ID" --app-secret-stdin --brand feishu

lark-cli config show
```

## 6. 创建 systemd 服务

复制示例服务文件：

```bash
sudo cp deploy/feishu-codex.service /etc/systemd/system/feishu-codex-bridge.service
```

如果安装路径或运行用户不同，请先编辑 service 文件。

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now feishu-codex-bridge
sudo systemctl status feishu-codex-bridge --no-pager
```

查看日志：

```bash
journalctl -u feishu-codex-bridge -f
```

看到下面这行表示飞书长连接已经建立：

```text
[lark-cli] ✅ 事件订阅已连接
```

## 7. 冒烟测试

在飞书里发送：

```text
/status
```

然后发送：

```text
hello, reply with one sentence
```

确认消息和卡片链路正常前，建议保持 `DEFAULT_MODE=plan`。

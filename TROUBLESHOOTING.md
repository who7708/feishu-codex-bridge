# 故障排查

[English](TROUBLESHOOTING_EN.md)

## 机器人连着但不回消息

先看服务日志里有没有 `[收到消息]`：

```bash
journalctl -u feishu-codex-bridge -f
```

- 没有：通常是飞书事件没有到达 bridge。
- 有：通常是 Codex、卡片更新或权限模式的问题。

### 检查飞书 App 配置

`main.py` 发消息使用 `.env` 里的 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`，收消息使用 `lark-cli event +subscribe`。如果 `lark-cli` 的全局配置指向另一个 App，bridge 可能显示已连接，但收不到当前机器人的消息。

```bash
cd /opt/feishu-codex-bridge
lark-cli config show | grep appId
grep FEISHU_APP_ID .env
```

两个 App ID 必须一致。不一致时，重新初始化 `lark-cli`：

```bash
set -a
source .env
set +a

printf '%s' "$FEISHU_APP_SECRET" |
  lark-cli config init --app-id "$FEISHU_APP_ID" --app-secret-stdin --brand feishu
```

还需要确认：

- 飞书开放平台启用了机器人能力。
- 已导入 [config/feishu_permissions.json](config/feishu_permissions.json) 中的权限。
- 在「事件与回调」中，「事件」和「回调」都选择了长连接模式。
- 已订阅事件：`im.message.receive_v1`。
- 已启用回调：`card.action.trigger`。
- 应用已发布，且管理员审核通过。

## Codex 调用失败

确认 bridge 运行用户可以直接使用 Codex CLI：

```bash
codex --version
codex exec --skip-git-repo-check --json "hello"
```

如果日志提示无法访问 `~/.codex`，请确认运行 bridge 的用户就是登录 Codex 的用户。systemd 部署时尤其要检查 service 文件里的 `User`、`HOME` 和 `PATH`。

```bash
systemctl cat feishu-codex-bridge
```

## 服务没有启动或反复重启

查看状态：

```bash
systemctl status feishu-codex-bridge --no-pager
journalctl -u feishu-codex-bridge -n 120 --no-pager
```

常见原因：

- `.env` 缺少 `FEISHU_APP_ID` 或 `FEISHU_APP_SECRET`。
- `lark-cli` 没有配置到同一个 App。
- `codex` 或 `lark-cli` 不在 systemd 的 `PATH` 中。
- service 文件里的 `WorkingDirectory` 或 `ExecStart` 路径不对。

## 卡片按钮没反应

卡片按钮依赖 `card.action.trigger` 回调。

请检查：

- 飞书开放平台里「回调」已选择长连接模式。
- 已启用 `card.action.trigger` 回调。
- 服务日志里有 `[卡片回调]`。

如果按钮没有回调日志，通常是飞书应用回调配置问题，不是 Codex 执行问题。

## 图片无法分析

图片消息会先下载到本机临时路径，再通过 Codex CLI 的 `--image` 参数传入。

请检查：

- 已导入 [config/feishu_permissions.json](config/feishu_permissions.json) 中的权限。
- 飞书应用已发布且权限已生效。
- 日志里是否有 `下载图片失败`。

## 全权限模式太危险

`DEFAULT_MODE=danger` 会调用 `codex exec --dangerously-bypass-approvals-and-sandbox`。

建议只在个人可信机器人里使用。公开或共享部署建议保持默认配置：

```bash
DEFAULT_MODE=plan
```

或在飞书里切换：

```bash
/mode plan
/mode workspace
```

## systemd 常用命令

```bash
systemctl status feishu-codex-bridge --no-pager
journalctl -u feishu-codex-bridge -f

systemctl restart feishu-codex-bridge
systemctl stop feishu-codex-bridge
systemctl start feishu-codex-bridge
```

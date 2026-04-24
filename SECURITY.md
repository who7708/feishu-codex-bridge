# 安全策略

[English](SECURITY_EN.md)

## 报告安全问题

涉及密钥泄露、远程执行风险、权限绕过的问题，请不要直接开公开 issue。请通过仓库维护者提供的私密联系方式报告。

## 运行风险

这个 bridge 会在运行它的机器上执行 Codex。开启 `danger` 模式后，飞书消息可以触发本机 shell 命令和文件修改，并且没有交互式确认。

公开或共享部署建议保持：

```env
DEFAULT_MODE=plan
```

建议：

- 为这个 bridge 使用独立的飞书应用。
- 不要把机器人加入不可信群聊。
- 条件允许时，用专门的操作系统用户运行服务。
- 保护好 `.env`、`~/.codex` 和 `~/.lark-cli`。
- 切换到 `/mode workspace` 或 `/mode danger` 前先查看日志和运行范围。

## 密钥处理

不要提交：

- `.env`
- 飞书 App Secret
- Codex auth 文件
- `~/.codex/sessions`
- `~/.lark-cli/config.json`
- 生产日志

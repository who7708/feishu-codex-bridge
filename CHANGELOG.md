# 更新日志

[English](CHANGELOG_EN.md)

## 0.1.0 - 2026-04-24

首个 Codex bridge 开源版本，基于 `feishu-claudecode-bridge` 的 MIT 协议版本改造，并保留原始版权声明。

### 新增

- 支持通过飞书私聊、群聊和话题触发本机 Codex CLI。
- 支持飞书消息到 Codex 执行、流式卡片更新、最终回复展示的完整链路。
- 支持 `codex exec --json` 和 `codex exec resume --json`。
- 支持解析 Codex JSONL 事件，展示文本增量、工具调用和命令执行进度。
- 支持读取 `--output-last-message` 生成的最终回复。
- 支持图片消息下载，并通过 Codex CLI `--image` 参数传入。
- 支持扫描 `~/.codex/sessions/**/*.jsonl` 和 `session_index.jsonl`，用于会话发现和恢复。
- 支持按 chat/topic 记录 workspace、model、mode、Codex session 等上下文状态。
- 支持 `/new`、`/resume`、`/model`、`/mode`、`/status`、`/cd`、`/ws`、`/stop`、`/mcp`、`/skills`、`/plugins`、`/usage` 等命令。
- 支持 `/stop` 终止正在运行的 Codex 进程。
- 提供飞书权限导入配置文件：`config/feishu_permissions.json`。
- 提供 Linux + systemd 部署文档，适合云服务器 7x24 小时待命运行。

### 安全与默认行为

- 默认权限模式为 `plan`，避免开源默认配置直接进入全权限自动执行。
- 支持切换 `plan`、`workspace`、`danger` 等权限模式。
- README 和部署文档明确提示 `danger` / 全权限自动模式风险。
- `.env.example` 不包含真实凭证。

### 文档

- 新增中文默认 README，并提供英文版本 `README_EN.md`。
- 新增产品规划文档 `docs/PRODUCT_PLAN.md` 和英文版本 `docs/PRODUCT_PLAN_EN.md`。
- 新增 Linux 部署文档 `docs/DEPLOY_LINUX.md` 和英文版本 `docs/DEPLOY_LINUX_EN.md`。
- 新增贡献指南、安全策略、故障排查和更新日志的中英文版本。

### 测试

- 建立基于 pytest 的测试套件。
- 覆盖 Codex runner、session store、命令处理和飞书消息主流程。
- 测试不依赖真实飞书服务或真实 Codex 网络调用。

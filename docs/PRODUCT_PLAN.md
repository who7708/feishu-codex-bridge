# Feishu Codex Bridge 产品计划

[English](PRODUCT_PLAN_EN.md)

## 产品目标

Feishu Codex Bridge 让用户可以从飞书/飞书国际版操作本机或服务器上的 Codex CLI。Bridge 运行在用户自己的机器上，通过 `lark-cli` WebSocket 事件接收飞书消息，调用本地 `codex` 可执行文件，并把进度流式更新到飞书卡片。

目标用户是希望从飞书里检查、修改、审阅或调试项目的工程师。产品复用用户已有的 Codex 登录态和本地文件系统权限，不提供托管云端 Codex runtime。

## 目标用户与场景

- 开发者在飞书私聊里让 Codex 检查或修改项目。
- 项目群里 @ 机器人，Codex 在该群绑定的工作空间内执行。
- 话题线程映射到独立 Codex session，避免上下文串话。
- 用户发送截图或图片，Codex 以 image input 接收。
- 用户用 `/stop` 停止长任务。
- 用户从飞书恢复或切换 session、模型、权限模式和工作空间。

## 范围内

- 飞书私聊、群聊和话题线程处理。
- Codex 文本和工具进度的流式卡片输出。
- 下载飞书图片并通过 `--image` 转发给 Codex。
- 基于 `~/.codex/sessions` 和 `~/.codex/session_index.jsonl` 的 session 持久化与 `/resume`。
- `/cd`、`/ls`、`/workspace`、`/ws` 工作空间管理。
- `/stop` 运行控制，以及同一 chat 新消息自动打断旧任务。
- Codex 元信息命令：`/model`、`/mode`、`/mcp`、`/skills`、`/plugins`、`/usage`。
- 通过同一 Codex runner 支持文档评论回复。
- Linux systemd 部署示例与运维文档，适合云服务器 7x24 小时运行。

## 范围外

- Web 管理后台。
- 多用户审批或 RBAC 系统。
- 托管云端 Codex 执行环境。
- 跨机器同步 session。
- 修改或迁移现有 Claude bridge。
- 除读取消息图片和回复评论外，直接编辑飞书文件。

## 权限与安全边界

公开发布默认模式是 `plan`。私有部署可以主动切换到 `workspace` 或 `danger`。其中 `danger` 会调用 Codex 的 `--dangerously-bypass-approvals-and-sandbox`，允许飞书消息触发本机文件修改和命令执行，且没有交互式确认。

Bridge 必须在 README 和 `/mode` 输出里明确提示该风险。更保守的模式必须始终可用：

- `plan`：只读规划，不写文件。
- `workspace`：Codex full-auto 的工作区可写模式。
- `danger`：跳过 approvals 和 sandbox 的全自动执行。

所有模式都运行在用户自己的机器上，使用用户自己的 Codex 凭证。Bridge 除飞书应用凭证外，不额外提供远程认证层。

## 飞书交互规则

- 私聊消息默认发给机器人。
- 群聊消息需要显式 @ 机器人；未 @ 消息应由飞书事件配置或本地 mention stripping 忽略。
- 话题群使用 `thread_id` 或 `root_id` 作为 chat key 的一部分，避免不同话题 session 泄漏。
- 第一个机器人回复是 loading card；后续输出 patch 同一张卡片。
- 如果最终卡片更新失败，bridge 回退为普通飞书回复。
- 卡片按钮回复视为同一 chat/session 的后续消息。

## Codex CLI 映射

- 新运行：`codex exec --json -C <cwd> -`。
- 恢复运行：`codex exec resume --json <session_id> -`。
- 最终回复捕获：`--output-last-message <tempfile>`。
- 模型选择：`-m <model>`。
- 图片输入：每张下载后的图片对应一个 `--image <path>`。
- 规划模式：`--sandbox read-only`。
- 工作区模式：`--full-auto`。
- Danger 模式：`--dangerously-bypass-approvals-and-sandbox`。

Runner 从 stdout 读取 JSONL 事件用于流式进度展示；如果最终回复文件存在，则以该文件内容作为权威最终回复。

## 错误处理

- Codex 非零退出但已有部分输出时，返回部分输出并附加错误提示。
- Codex 非零退出且没有输出时，抛出包含 stderr 的清晰错误。
- 访问 `~/.codex` 的权限失败会被改写为用户可读提示，说明 bridge 进程需要访问 Codex session 文件。
- 长时间无输出会终止 Codex 进程并报告 timeout。
- `/stop` 先优雅终止当前进程，短暂等待后强制 kill。

## 验收标准

- 在没有真实飞书或真实 Codex 网络调用的情况下，`pytest` 在 `feishu-codex-bridge` 内通过。
- `docs/PRODUCT_PLAN.md` 能回答产品做什么、不做什么、如何验收。
- `README.md` 说明 `danger` 全权限风险和更安全的模式选择。
- 不修改现有 `feishu-claudecode-bridge` 目录。
- 测试覆盖 runner 命令组装、JSONL 解析、session 扫描、命令处理和飞书到 Codex 的主消息流。

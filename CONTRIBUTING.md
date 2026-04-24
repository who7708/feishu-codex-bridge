# 贡献指南

[English](CONTRIBUTING_EN.md)

感谢你帮助改进 Feishu Codex Bridge。

## 本地开发

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest
python3 -m pytest -q
```

测试应当可以在没有真实飞书凭证、没有真实 Codex 网络调用的情况下运行。

## Pull Request

- 保持改动范围清晰。
- 行为变更需要添加或更新测试。
- 不要提交 `.env`、token、App Secret、session 文件、日志或本地缓存。
- 尽量保留当前模块边界：runner、commands、session store、Feishu client 和 main event flow。

## 安全相关改动

如果改动涉及权限模式、进程执行、图片/文件处理或飞书事件路由，请同时补测试；如果用户可见行为改变，也请更新 README。

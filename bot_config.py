import os
import shutil

from dotenv import load_dotenv

load_dotenv()

FEISHU_APP_ID = os.environ["FEISHU_APP_ID"]
FEISHU_APP_SECRET = os.environ["FEISHU_APP_SECRET"]

CODEX_CLI = os.getenv("CODEX_CLI_PATH") or shutil.which("codex") or "codex"

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-6-luna")
DEFAULT_CWD = os.path.expanduser(os.getenv("DEFAULT_CWD", "~"))
DEFAULT_MODE = os.getenv("DEFAULT_MODE", os.getenv("PERMISSION_MODE", "plan"))
PERMISSION_MODE = DEFAULT_MODE

# 对话全文可能包含业务数据，默认只记录处理阶段和长度；仅在本机排障时显式开启。
LOG_CONVERSATION_CONTENT = os.getenv("LOG_CONVERSATION_CONTENT", "false").strip().lower() in {
    "1", "true", "yes", "on",
}

SESSIONS_DIR = os.path.expanduser("~/.feishu-codex")

# 查询配置目录固定指向数据库环境文件所在位置，避免用户切换会话工作目录时串用连接配置。
TICKET_DB_CONFIG_DIR = os.path.abspath(
    os.path.expanduser(os.getenv("TICKET_DB_CONFIG_DIR", DEFAULT_CWD))
)
TICKET_MCP_SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ticket_mcp.py")

CALLBACK_PORT = int(os.getenv("CALLBACK_PORT", "9982"))
STREAM_CHUNK_SIZE = int(os.getenv("STREAM_CHUNK_SIZE", "20"))

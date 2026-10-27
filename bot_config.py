import os
import shutil

from dotenv import load_dotenv

load_dotenv()

FEISHU_APP_ID = os.environ["FEISHU_APP_ID"]
FEISHU_APP_SECRET = os.environ["FEISHU_APP_SECRET"]

CODEX_CLI = os.getenv("CODEX_CLI_PATH") or shutil.which("codex") or "codex"

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-5.6-luna")
DEFAULT_CWD = os.path.expanduser(os.getenv("DEFAULT_CWD", "~"))
DEFAULT_MODE = os.getenv("DEFAULT_MODE", os.getenv("PERMISSION_MODE", "plan"))
PERMISSION_MODE = DEFAULT_MODE

SESSIONS_DIR = os.path.expanduser("~/.feishu-codex")

CALLBACK_PORT = int(os.getenv("CALLBACK_PORT", "9982"))
STREAM_CHUNK_SIZE = int(os.getenv("STREAM_CHUNK_SIZE", "20"))

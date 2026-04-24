import pytest
import json
import os
import sys

# Set test environment variables before importing
os.environ.setdefault("FEISHU_APP_ID", "test_app_id")
os.environ.setdefault("FEISHU_APP_SECRET", "test_app_secret")
os.environ.setdefault("DEFAULT_MODEL", "gpt-5.5")
os.environ.setdefault("DEFAULT_MODE", "plan")

# Add parent directory to path to import session_store
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import session_store as session_store_module
from bot_config import DEFAULT_MODEL, PERMISSION_MODE
from session_store import SessionStore, scan_cli_sessions


@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    """Create a temporary session store for testing"""
    sessions_dir = tmp_path / "bridge-state"
    sessions_dir.mkdir()
    monkeypatch.setattr(session_store_module, "SESSIONS_DIR", str(sessions_dir))
    monkeypatch.setattr(session_store_module, "SESSIONS_FILE", str(sessions_dir / "sessions.json"))
    store = SessionStore()
    yield store


@pytest.mark.asyncio
async def test_get_current_with_chat_id_private(temp_store):
    """Test getting current session for private chat"""
    user_id = "user_123"
    chat_id = "user_123"

    session = await temp_store.get_current(user_id, chat_id)
    assert session.model == DEFAULT_MODEL
    assert session.permission_mode == PERMISSION_MODE


@pytest.mark.asyncio
async def test_get_current_with_chat_id_group(temp_store):
    """Test getting current session for group chat"""
    user_id = "user_123"
    chat_id = "group_456"

    session = await temp_store.get_current(user_id, chat_id)
    assert session.model == DEFAULT_MODEL
    assert session.permission_mode == PERMISSION_MODE


@pytest.mark.asyncio
async def test_session_isolation_between_chats(temp_store):
    """Test that private and group sessions are isolated"""
    user_id = "user_123"
    private_chat_id = "user_123"
    group_chat_id = "group_456"

    await temp_store.set_model(user_id, private_chat_id, "gpt-5.4")
    await temp_store.set_model(user_id, group_chat_id, "gpt-5.3-codex")

    private_session = await temp_store.get_current(user_id, private_chat_id)
    group_session = await temp_store.get_current(user_id, group_chat_id)

    assert private_session.model == "gpt-5.4"
    assert group_session.model == "gpt-5.3-codex"


@pytest.mark.asyncio
async def test_set_model_with_chat_id(temp_store):
    """Test setting model for specific chat"""
    user_id = "user_123"
    chat_id = "group_456"

    await temp_store.set_model(user_id, chat_id, "gpt-5.4")

    session = await temp_store.get_current(user_id, chat_id)
    assert session.model == "gpt-5.4"


@pytest.mark.asyncio
async def test_set_permission_mode_with_chat_id(temp_store):
    user_id = "user_123"
    chat_id = "group_456"

    await temp_store.set_permission_mode(user_id, chat_id, "plan")
    session = await temp_store.get_current(user_id, chat_id)
    assert session.permission_mode == "plan"


@pytest.mark.asyncio
async def test_set_cwd_with_chat_id(temp_store):
    user_id = "user_123"
    chat_id = "group_456"

    await temp_store.set_cwd(user_id, chat_id, "/tmp")
    session = await temp_store.get_current(user_id, chat_id)
    assert session.cwd == "/tmp"


@pytest.mark.asyncio
async def test_new_session_with_chat_id(temp_store):
    user_id = "user_123"
    chat_id = "group_456"

    await temp_store.set_model(user_id, chat_id, "gpt-5.4")
    await temp_store.new_session(user_id, chat_id)

    session = await temp_store.get_current(user_id, chat_id)
    assert session.session_id is None


@pytest.mark.asyncio
async def test_list_sessions_with_chat_id(temp_store):
    user_id = "user_123"
    chat_id = "group_456"

    sessions = await temp_store.list_sessions(user_id, chat_id)
    assert len(sessions) == 0

    await temp_store.set_model(user_id, chat_id, "gpt-5.4")
    raw = await temp_store.get_current_raw(user_id, chat_id)
    raw["session_id"] = "test_session_123"
    temp_store._save()

    await temp_store.new_session(user_id, chat_id)

    sessions = await temp_store.list_sessions(user_id, chat_id)
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "test_session_123"


def test_scan_cli_sessions_reads_codex_jsonl(tmp_path, monkeypatch):
    sessions_dir = tmp_path / ".codex" / "sessions" / "2026" / "04" / "24"
    sessions_dir.mkdir(parents=True)
    sid = "019dbe65-754d-7251-a4a1-406bc6ea4a5b"
    session_file = sessions_dir / f"rollout-2026-04-24T15-30-13-{sid}.jsonl"
    session_file.write_text(
        "\n".join([
            json.dumps({
                "timestamp": "2026-04-24T07:30:13.497Z",
                "type": "session_meta",
                "payload": {"id": sid, "cwd": "/tmp/project", "timestamp": "2026-04-24T07:30:13.497Z"},
            }),
            json.dumps({
                "timestamp": "2026-04-24T07:31:00.000Z",
                "type": "user_msg",
                "payload": {"message": "帮我实现 Codex bridge"},
            }),
        ]),
        encoding="utf-8",
    )
    monkeypatch.setattr(session_store_module, "CODEX_SESSIONS_DIR", str(tmp_path / ".codex" / "sessions"))

    sessions = scan_cli_sessions(10)

    assert len(sessions) == 1
    assert sessions[0]["session_id"] == sid
    assert sessions[0]["cwd"] == "/tmp/project"
    assert sessions[0]["preview"] == "帮我实现 Codex bridge"

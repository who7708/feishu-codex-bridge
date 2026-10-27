"""
Integration tests for group chat functionality.
Tests message handling, session isolation, and chat detection.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock

# Set environment variables before importing modules
os.environ.setdefault("FEISHU_APP_ID", "test_app_id")
os.environ.setdefault("FEISHU_APP_SECRET", "test_app_secret")
os.environ.setdefault("FEISHU_VERIFICATION_TOKEN", "test_token")
os.environ.setdefault("FEISHU_ENCRYPT_KEY", "test_key")

from main import extract_chat_info, handle_message_from_cli
import session_store as session_store_module
from session_store import SessionStore


@pytest.fixture
def session_store(tmp_path, monkeypatch):
    """Create a session store for testing"""
    sessions_dir = tmp_path / "bridge-state"
    sessions_dir.mkdir()
    monkeypatch.setattr(session_store_module, "SESSIONS_DIR", str(sessions_dir))
    monkeypatch.setattr(session_store_module, "SESSIONS_FILE", str(sessions_dir / "sessions.json"))
    return SessionStore()


# ── Test extract_chat_info ──────────────────────────────────

def test_extract_chat_info_private_chat():
    """Test extracting chat info from private chat message"""
    mock_event = MagicMock()
    mock_event.event.sender.sender_id.open_id = "user_123"
    mock_event.event.message.chat_type = "p2p"
    mock_event.event.message.chat_id = "user_123"

    user_id, chat_id, is_group = extract_chat_info(mock_event)

    assert user_id == "user_123"
    assert chat_id == "user_123"
    assert is_group is False


def test_extract_chat_info_group_chat():
    """Test extracting chat info from group chat message"""
    mock_event = MagicMock()
    mock_event.event.sender.sender_id.open_id = "user_456"
    mock_event.event.message.chat_type = "group"
    mock_event.event.message.chat_id = "group_789"

    user_id, chat_id, is_group = extract_chat_info(mock_event)

    assert user_id == "user_456"
    assert chat_id == "group_789"
    assert is_group is True


# ── Test session isolation ──────────────────────────────────

@pytest.mark.asyncio
async def test_session_isolation_private_vs_group(session_store):
    """Test that private and group chats have isolated sessions"""
    user_id = "user_123"
    private_chat_id = user_id
    group_chat_id = "group_456"

    await session_store.set_model(user_id, private_chat_id, "gpt-5.5")
    await session_store.set_model(user_id, group_chat_id, "gpt-5.4-mini")

    private_check = await session_store.get_current(user_id, private_chat_id)
    group_check = await session_store.get_current(user_id, group_chat_id)

    assert private_check.model == "gpt-5.5"
    assert group_check.model == "gpt-5.4-mini"


@pytest.mark.asyncio
async def test_multiple_groups_isolation(session_store):
    """Test that multiple groups have independent sessions"""
    user_id = "user_123"
    group1_id = "group_001"
    group2_id = "group_002"

    await session_store.set_model(user_id, group1_id, "gpt-5.5")
    await session_store.set_model(user_id, group2_id, "gpt-5.4-mini")

    group1_session = await session_store.get_current(user_id, group1_id)
    group2_session = await session_store.get_current(user_id, group2_id)

    assert group1_session.model == "gpt-5.5"
    assert group2_session.model == "gpt-5.4-mini"


@pytest.mark.asyncio
async def test_multiple_users_in_same_group(session_store):
    """同群成员共享 Codex session，但保留各自的模型设置。"""
    group_id = "group_123"
    user1_id = "user_001"
    user2_id = "user_002"

    await session_store.set_model(user1_id, group_id, "gpt-5.5")
    await session_store.set_model(user2_id, group_id, "gpt-5.4-mini")

    user1_session = await session_store.get_current(user1_id, group_id)
    user2_session = await session_store.get_current(user2_id, group_id)

    assert user1_session.model == "gpt-5.5"
    assert user2_session.model == "gpt-5.4-mini"


@pytest.mark.asyncio
async def test_group_topics_share_group_chat_session_key(monkeypatch):
    import main

    monkeypatch.setattr(main, "_chat_locks", {})
    monkeypatch.setattr(main, "_seen_message_ids", set())
    seen_chat_ids = []

    async def capture_message(user_id, chat_id, *args):
        seen_chat_ids.append(chat_id)

    monkeypatch.setattr(main, "_process_message_cli", capture_message)
    for message_id, topic_id, user_id in (
        ("msg_topic_a", "omt_topic_a", "user_123"),
        ("msg_topic_b", "omt_topic_b", "user_456"),
    ):
        await handle_message_from_cli({
            "message_type": "text",
            "chat_type": "group",
            "user_id": user_id,
            "chat_id": "oc_group_456",
            "message_id": message_id,
            "content": {"text": "hello"},
            "thread_id": topic_id,
        })

    assert seen_chat_ids == ["oc_group_456", "oc_group_456"]


@pytest.mark.asyncio
async def test_group_codex_session_shared_across_members_and_new_resets_group(session_store):
    group_id = "oc_shared_group"

    await session_store.on_codex_response("user_001", group_id, "shared_codex_session", "question")

    member_session = await session_store.get_current("user_002", group_id)
    assert member_session.session_id == "shared_codex_session"
    await session_store.on_codex_response("user_001", "user_001", "private_session", "private question")
    other_group = await session_store.get_current("user_001", "oc_other_group")
    assert other_group.session_id is None

    await session_store.new_session("user_002", group_id)
    owner_session = await session_store.get_current("user_001", group_id)
    private_session = await session_store.get_current("user_001", "user_001")
    assert owner_session.session_id is None
    assert private_session.session_id == "private_session"
    assert [entry["session_id"] for entry in await session_store.list_sessions("user_001", group_id)] == [
        "shared_codex_session"
    ]


@pytest.mark.asyncio
async def test_group_session_does_not_auto_migrate_legacy_topic_session(session_store):
    user_id = "user_legacy_group"
    legacy_key = "oc_legacy_group:omt_old_topic"
    session_store._data[user_id] = {
        legacy_key: {
            "current": {"session_id": "old_topic_session", "model": "gpt-5.5"},
            "history": [],
        }
    }

    group_session = await session_store.get_current(user_id, "oc_legacy_group")

    assert group_session.session_id is None
    assert session_store._data[user_id][legacy_key]["current"]["session_id"] == "old_topic_session"


# ── Test session operations with chat_id ──────────────────

@pytest.mark.asyncio
async def test_set_permission_mode_with_chat_id(session_store):
    """Test setting permission mode for specific chat"""
    user_id = "user_123"
    chat_id = "group_456"

    await session_store.set_permission_mode(user_id, chat_id, "restricted")
    session = await session_store.get_current(user_id, chat_id)

    assert session.permission_mode == "restricted"


@pytest.mark.asyncio
async def test_set_cwd_with_chat_id(session_store):
    """Test setting working directory for specific chat"""
    user_id = "user_123"
    chat_id = "group_456"

    await session_store.set_cwd(user_id, chat_id, "/tmp/work")
    session = await session_store.get_current(user_id, chat_id)

    assert session.cwd == "/tmp/work"


@pytest.mark.asyncio
async def test_new_session_with_chat_id(session_store):
    """Test creating new session for specific chat"""
    user_id = "user_123"
    chat_id = "group_456"

    await session_store.new_session(user_id, chat_id)
    session = await session_store.get_current(user_id, chat_id)

    assert session.session_id is None


@pytest.mark.asyncio
async def test_list_sessions_with_chat_id(session_store):
    """Test listing sessions for specific chat"""
    user_id = "user_list_test"
    chat_id = "group_list_test"

    sessions = await session_store.list_sessions(user_id, chat_id)
    assert isinstance(sessions, list)


@pytest.mark.asyncio
async def test_resume_session_with_chat_id(session_store):
    """Test resuming session in specific chat"""
    user_id = "user_resume_test"
    chat_id = "group_resume_test"

    resumed_id, old_title = await session_store.resume_session(user_id, chat_id, "1")
    assert resumed_id is None
    assert old_title == ""

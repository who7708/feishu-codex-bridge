from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("FEISHU_APP_ID", "test_app_id")
os.environ.setdefault("FEISHU_APP_SECRET", "test_app_secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_event(
    user_id: str = "user_001",
    chat_id: str = "user_001",
    chat_type: str = "p2p",
    text: str = "hello",
    message_id: str = "msg_001",
    mentions: list | None = None,
):
    event = MagicMock()
    event.event.sender.sender_id.open_id = user_id
    event.event.message.chat_type = chat_type
    event.event.message.chat_id = chat_id
    event.event.message.message_type = "text"
    event.event.message.content = json.dumps({"text": text})
    event.event.message.message_id = message_id
    event.event.message.mentions = mentions or []
    return event


@pytest.mark.asyncio
async def test_private_chat_full_flow_updates_reply_card():
    from main import _chat_locks, _seen_message_ids, handle_message_async

    _chat_locks.clear()
    _seen_message_ids.clear()
    event = _make_event(text="你好，帮我看看代码")
    card_updates = []

    with patch("main._add_reaction", new_callable=AsyncMock), \
         patch("main.feishu") as mock_feishu, \
         patch("main.store") as mock_store, \
         patch("main.run_codex", new_callable=AsyncMock) as mock_run:

        mock_feishu.reply_card = AsyncMock(return_value="card_msg_001")
        mock_feishu.update_card = AsyncMock(side_effect=lambda mid, content: card_updates.append(content))
        mock_run.return_value = ("代码看起来没问题，测试也通过了。", "sid_abc123", False)

        mock_session = MagicMock()
        mock_session.session_id = None
        mock_session.model = "gpt-5.5"
        mock_session.cwd = "/tmp"
        mock_session.permission_mode = "danger"
        mock_store.get_current = AsyncMock(return_value=mock_session)
        mock_store.on_codex_response = AsyncMock()

        await handle_message_async(event)

    mock_feishu.reply_card.assert_called_once()
    assert card_updates[-1] == "代码看起来没问题，测试也通过了。"
    mock_run.assert_awaited_once()
    mock_store.on_codex_response.assert_awaited_once_with("user_001", "user_001", "sid_abc123", "你好，帮我看看代码")


@pytest.mark.asyncio
async def test_group_chat_strips_mention_before_codex():
    from main import _chat_locks, _seen_message_ids, handle_message_async

    _chat_locks.clear()
    _seen_message_ids.clear()
    event = _make_event(
        user_id="user_001",
        chat_id="group_001",
        chat_type="group",
        text="@_user_1 帮我看看这段代码",
        message_id="group_msg_001",
        mentions=[{"key": "@_user_1"}],
    )

    with patch("main._add_reaction", new_callable=AsyncMock), \
         patch("main.feishu") as mock_feishu, \
         patch("main.store") as mock_store, \
         patch("main.run_codex", new_callable=AsyncMock) as mock_run:

        mock_feishu.reply_card = AsyncMock(return_value="reply_card_001")
        mock_feishu.update_card = AsyncMock()
        mock_run.return_value = ("代码没问题", "sid_group", False)

        mock_session = MagicMock()
        mock_session.session_id = None
        mock_session.model = "gpt-5.5"
        mock_session.cwd = "/tmp"
        mock_session.permission_mode = "danger"
        mock_store.get_current = AsyncMock(return_value=mock_session)
        mock_store.on_codex_response = AsyncMock()

        await handle_message_async(event)

    assert mock_run.await_args.kwargs["message"] == "帮我看看这段代码"
    mock_store.on_codex_response.assert_awaited_once_with("user_001", "group_001", "sid_group", "帮我看看这段代码")


@pytest.mark.asyncio
async def test_group_slash_command_uses_group_session():
    from main import _chat_locks, _seen_message_ids, handle_message_async

    _chat_locks.clear()
    _seen_message_ids.clear()
    event = _make_event(
        user_id="user_001",
        chat_id="group_001",
        chat_type="group",
        text="@_user_1 /model spark",
        message_id="group_msg_002",
        mentions=[{"key": "@_user_1"}],
    )

    with patch("main.feishu") as mock_feishu, \
         patch("main.store") as mock_store:
        mock_feishu.reply_card = AsyncMock(return_value="reply_card_002")
        mock_store.set_model = AsyncMock()

        await handle_message_async(event)

    mock_store.set_model.assert_awaited_once_with("user_001", "group_001", "gpt-5.3-codex-spark")
    mock_feishu.reply_card.assert_awaited_once()


@pytest.mark.asyncio
async def test_image_message_forwards_image_path_to_codex():
    from main import _chat_locks, _seen_message_ids, handle_message_async

    _chat_locks.clear()
    _seen_message_ids.clear()
    event = MagicMock()
    event.event.sender.sender_id.open_id = "user_001"
    event.event.message.chat_type = "p2p"
    event.event.message.chat_id = "user_001"
    event.event.message.message_type = "image"
    event.event.message.content = json.dumps({"image_key": "img_001"})
    event.event.message.message_id = "img_msg_001"
    event.event.message.mentions = []

    img_path = "/tmp/feishu-img-test.png"
    with open(img_path, "wb") as f:
        f.write(b"fake-image")

    with patch("main.feishu") as mock_feishu, \
         patch("main.store") as mock_store, \
         patch("main.run_codex", new_callable=AsyncMock) as mock_run:

        mock_feishu.download_image = AsyncMock(return_value=img_path)
        mock_feishu.reply_card = AsyncMock(return_value="card_img_001")
        mock_feishu.update_card = AsyncMock()
        mock_run.return_value = ("图片里是错误截图", "sid_img", False)

        mock_session = MagicMock()
        mock_session.session_id = None
        mock_session.model = "gpt-5.5"
        mock_session.cwd = "/tmp"
        mock_session.permission_mode = "danger"
        mock_store.get_current = AsyncMock(return_value=mock_session)
        mock_store.on_codex_response = AsyncMock()

        await handle_message_async(event)

    assert mock_run.await_args.kwargs["images"] == [img_path]

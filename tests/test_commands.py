import json
import os
import sys
from unittest.mock import Mock

import pytest

os.environ.setdefault("FEISHU_APP_ID", "test_app_id")
os.environ.setdefault("FEISHU_APP_SECRET", "test_app_secret")
os.environ.setdefault("DEFAULT_MODEL", "gpt-5.5")
os.environ.setdefault("DEFAULT_MODE", "plan")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import commands as commands_module
import session_store as session_store_module
from commands import handle_command
from session_store import SessionStore


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "state"
    sessions_dir.mkdir()
    monkeypatch.setattr(session_store_module, "SESSIONS_DIR", str(sessions_dir))
    monkeypatch.setattr(session_store_module, "SESSIONS_FILE", str(sessions_dir / "sessions.json"))
    return SessionStore()


@pytest.mark.asyncio
async def test_mode_lists_codex_modes_and_warns_about_danger(isolated_store):
    reply = await handle_command("mode", "", "user_1", "chat_1", isolated_store)

    assert "danger" in reply
    assert "全权限自动" in reply
    assert "风险" in reply


@pytest.mark.asyncio
async def test_mode_aliases_full_permissions(isolated_store):
    reply = await handle_command("mode", "bypass", "user_1", "chat_1", isolated_store)
    cur = await isolated_store.get_current("user_1", "chat_1")

    assert "danger" in reply
    assert cur.permission_mode == "danger"


@pytest.mark.asyncio
async def test_model_aliases_codex_models(isolated_store):
    reply = await handle_command("model", "spark", "user_1", "chat_1", isolated_store)
    cur = await isolated_store.get_current("user_1", "chat_1")

    assert "gpt-5.3-codex-spark" in reply
    assert cur.model == "gpt-5.3-codex-spark"


@pytest.mark.asyncio
async def test_mcp_uses_codex_cli(monkeypatch, isolated_store):
    completed = Mock(stdout="computer-use enabled\n")

    def fake_run(args, **kwargs):
        assert args[:3] == ["codex", "mcp", "list"]
        return completed

    monkeypatch.setattr(commands_module, "CODEX_CLI", "codex")
    monkeypatch.setattr(commands_module.subprocess, "run", fake_run)

    reply = await handle_command("mcp", "", "user_1", "chat_1", isolated_store)

    assert "Codex MCP" in reply
    assert "computer-use enabled" in reply


@pytest.mark.asyncio
async def test_skills_scans_codex_skills(tmp_path, monkeypatch, isolated_store):
    skill_dir = tmp_path / "skills" / ".system" / "imagegen"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# imagegen\nGenerate images.", encoding="utf-8")
    monkeypatch.setattr(commands_module, "SKILLS_DIR", str(tmp_path / "skills"))

    reply = await handle_command("skills", "", "user_1", "chat_1", isolated_store)

    assert "Codex Skills" in reply
    assert "imagegen" in reply


@pytest.mark.asyncio
async def test_plugins_scans_codex_plugin_metadata(tmp_path, monkeypatch, isolated_store):
    plugin_dir = tmp_path / "plugins" / "cache" / "openai-bundled" / "browser-use" / "1" / ".codex-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(json.dumps({"name": "browser-use", "description": "Browser"}), encoding="utf-8")
    monkeypatch.setattr(commands_module, "PLUGINS_CACHE_DIR", str(tmp_path / "plugins" / "cache"))

    reply = await handle_command("plugins", "", "user_1", "chat_1", isolated_store)

    assert "Codex Plugins" in reply
    assert "browser-use" in reply


@pytest.mark.asyncio
async def test_usage_reads_latest_local_rate_limit(tmp_path, monkeypatch, isolated_store):
    sid = "019dbe65-754d-7251-a4a1-406bc6ea4a5b"
    sessions_dir = tmp_path / ".codex" / "sessions" / "2026" / "04" / "24"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / f"rollout-2026-04-24T15-30-13-{sid}.jsonl").write_text(
        json.dumps({
            "timestamp": "2026-04-24T07:32:09.422Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "limit_id": "codex",
                    "primary": {"used_percent": 4.0, "window_minutes": 300, "resets_at": 1777019444},
                    "secondary": {"used_percent": 7.0, "window_minutes": 10080, "resets_at": 1777425894},
                },
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(commands_module, "CODEX_SESSIONS_DIR", str(tmp_path / ".codex" / "sessions"))

    reply = await handle_command("usage", "", "user_1", "chat_1", isolated_store)

    assert "Codex 用量" in reply
    assert "4.0%" in reply
    assert "7.0%" in reply

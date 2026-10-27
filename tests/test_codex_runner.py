import asyncio
import os
import sys

import pytest

os.environ.setdefault("FEISHU_APP_ID", "test_app_id")
os.environ.setdefault("FEISHU_APP_SECRET", "test_app_secret")
os.environ.setdefault("DEFAULT_MODEL", "gpt-5.5")
os.environ.setdefault("DEFAULT_MODE", "plan")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codex_runner import run_codex


class FakeStdin:
    def __init__(self):
        self.buffer = b""
        self.closed = False

    def write(self, data: bytes):
        self.buffer += data

    async def drain(self):
        return None

    def close(self):
        self.closed = True


class FakeStdout:
    def __init__(self, lines: list[bytes]):
        self._lines = list(lines)
        self._index = 0

    async def readline(self):
        if self._index >= len(self._lines):
            return b""
        line = self._lines[self._index]
        self._index += 1
        return line


class FakeStderr:
    def __init__(self, data: bytes):
        self._data = data

    async def read(self):
        return self._data


class FakeProc:
    def __init__(self, stdout_lines: list[bytes], stderr: bytes = b"", returncode: int = 0):
        self.pid = 1234
        self.stdin = FakeStdin()
        self.stdout = FakeStdout(stdout_lines)
        self.stderr = FakeStderr(stderr)
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    async def wait(self):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


def test_run_codex_builds_new_exec_command(monkeypatch):
    proc = FakeProc([
        b'{"type":"session_meta","payload":{"id":"sid_123"}}\n',
        b'{"type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"Hello"}]}}\n',
    ])
    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        output_file = args[args.index("--output-last-message") + 1]
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("Hello final")
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr("codex_runner.CODEX_CLI", "codex")

    text, session_id, used_fallback = asyncio.run(
        run_codex("hi", model="gpt-5.5", cwd="/tmp/project", permission_mode="danger")
    )

    assert text == "Hello final"
    assert session_id == "sid_123"
    assert used_fallback is False
    assert captured["args"][:3] == ("codex", "exec", "--json")
    assert "--skip-git-repo-check" in captured["args"]
    assert "-C" in captured["args"]
    assert "/tmp/project" in captured["args"]
    assert "--dangerously-bypass-approvals-and-sandbox" in captured["args"]
    assert "-m" in captured["args"]
    assert "gpt-5.5" in captured["args"]
    assert "mcp_servers.feishu_ticket_db.enabled=true" in captured["args"]
    assert any("mcp_servers.feishu_ticket_db.command=" in arg for arg in captured["args"])
    assert any("mcp_servers.feishu_ticket_db.args=" in arg for arg in captured["args"])
    assert captured["kwargs"]["env"]["TICKET_DB_CONFIG_DIR"]
    assert proc.stdin.buffer == b"hi\n"
    assert proc.stdin.closed is True


def test_run_codex_builds_resume_command(monkeypatch):
    proc = FakeProc([b'{"type":"session_meta","payload":{"id":"sid_old"}}\n'])
    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        output_file = args[args.index("--output-last-message") + 1]
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("resumed answer")
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr("codex_runner.CODEX_CLI", "codex")

    text, session_id, _ = asyncio.run(run_codex("continue", session_id="sid_old"))

    assert text == "resumed answer"
    assert session_id == "sid_old"
    assert captured["args"][:4] == ("codex", "exec", "resume", "--json")
    assert "--skip-git-repo-check" in captured["args"]
    assert "sid_old" in captured["args"]


def test_run_codex_streams_text_and_tool_callbacks(monkeypatch, capsys):
    proc = FakeProc([
        b'{"type":"session_meta","payload":{"id":"sid_1"}}\n',
        b'{"type":"response_item","payload":{"type":"function_call","name":"exec_command","arguments":"{\\"cmd\\":\\"ls\\"}"}}\n',
        b'{"type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"Hello "}]}}\n',
        b'{"type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"world"}]}}\n',
    ])

    async def fake_create_subprocess_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    chunks = []
    tools = []

    async def collect_chunk(chunk):
        chunks.append(chunk)

    async def collect_tool(name, inp):
        tools.append((name, inp))

    text, session_id, _ = asyncio.run(
        run_codex("hi", on_text_chunk=collect_chunk, on_tool_use=collect_tool)
    )

    assert chunks == ["Hello ", "world"]
    assert tools == [("exec_command", {"cmd": "ls"})]
    assert text == "Hello world"
    assert session_id == "sid_1"
    logged = capsys.readouterr().out
    assert "type=response_item" in logged
    assert "Hello" not in logged


def test_run_codex_passes_images(monkeypatch):
    proc = FakeProc([])
    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    asyncio.run(run_codex("look", images=["/tmp/a.png", "/tmp/b.jpg"]))

    assert captured["args"].count("--image") == 2
    assert "/tmp/a.png" in captured["args"]
    assert "/tmp/b.jpg" in captured["args"]


def test_run_codex_returns_partial_output_on_nonzero_exit(monkeypatch):
    proc = FakeProc([
        b'{"type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"partial"}]}}\n',
    ], stderr=b"boom", returncode=1)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    text, _, _ = asyncio.run(run_codex("hi"))

    assert "partial" in text
    assert "boom" in text


def test_run_codex_raises_clear_codex_home_permission_error(monkeypatch):
    proc = FakeProc([], stderr=b"Codex cannot access session files at /Users/me/.codex/sessions", returncode=1)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(RuntimeError, match=r"Codex 无法访问 ~/.codex/sessions"):
        asyncio.run(run_codex("hi"))


def test_run_codex_attaches_process(monkeypatch):
    proc = FakeProc([])
    seen = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    async def on_start(p):
        seen.append(p)

    asyncio.run(run_codex("hi", on_process_start=on_start))

    assert seen == [proc]

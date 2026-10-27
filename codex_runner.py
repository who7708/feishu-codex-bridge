from __future__ import annotations

"""
Run the local Codex CLI and parse JSONL progress events.

The bridge reuses the user's existing Codex login and local ~/.codex state.
"""

import asyncio
import json
import os
import sys
import tempfile
import time
from typing import Callable, Optional

from bot_config import CODEX_CLI, DEFAULT_MODE, TICKET_DB_CONFIG_DIR, TICKET_MCP_SERVER

IDLE_TIMEOUT = 900


def _trace_log(message: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def _extract_text_content(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if not isinstance(item, dict):
                continue
            if item.get("type") in {"output_text", "text"}:
                parts.append(item.get("text", ""))
        return "".join(parts)
    return ""


def _extract_event_text(data: dict) -> str:
    payload = data.get("payload", data)
    if not isinstance(payload, dict):
        return ""
    if payload.get("type") not in {"message", "assistant_message"}:
        return ""
    return _extract_text_content(payload.get("content", ""))


def _extract_session_id(data: dict) -> Optional[str]:
    payload = data.get("payload", data)
    if not isinstance(payload, dict):
        return None
    if data.get("type") == "thread.started" or payload.get("type") == "thread.started":
        thread_id = data.get("thread_id") or payload.get("thread_id")
        if thread_id:
            return thread_id
    if data.get("type") == "session_meta" or payload.get("type") == "session_meta":
        sid = payload.get("id") or payload.get("session_id")
        if sid:
            return sid
    if payload.get("session_id"):
        return payload.get("session_id")
    return None


def _extract_tool_call(data: dict) -> tuple[str, dict] | None:
    payload = data.get("payload", data)
    if not isinstance(payload, dict):
        return None
    if payload.get("type") not in {"function_call", "tool_call"}:
        return None
    name = payload.get("name") or payload.get("tool_name") or ""
    raw_args = payload.get("arguments") or payload.get("input") or {}
    if isinstance(raw_args, str):
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            args = {}
    elif isinstance(raw_args, dict):
        args = raw_args
    else:
        args = {}
    return (name, args) if name else None


def _permission_args(mode: Optional[str], resume: bool = False) -> list[str]:
    normalized = (mode or DEFAULT_MODE or "plan").strip()
    aliases = {
        "read-only": "plan",
        "readonly": "plan",
        "safe": "plan",
        "full-auto": "workspace",
        "auto": "workspace",
        "bypass": "danger",
        "dontAsk": "danger",
    }
    normalized = aliases.get(normalized, normalized)
    if resume:
        # exec resume 不接受 --sandbox；用同等 sandbox_mode 配置覆盖本次恢复调用。
        if normalized == "danger":
            return ["--dangerously-bypass-approvals-and-sandbox"]
        sandbox_mode = "workspace-write" if normalized == "workspace" else "read-only"
        return ["--config", f'sandbox_mode="{sandbox_mode}"']
    if normalized == "plan":
        return ["--sandbox", "read-only"]
    if normalized == "workspace":
        return ["--sandbox", "workspace-write"]
    if normalized == "danger":
        return ["--dangerously-bypass-approvals-and-sandbox"]
    return ["--sandbox", "read-only"]


def _ticket_mcp_args() -> list[str]:
    """仅为当前 Codex 调用注册项目自带的只读票务 MCP，不写用户全局配置。"""
    def toml_literal(value: str) -> str:
        normalized = value.replace("\\", "/")
        if "'''" in normalized:
            raise ValueError("票务 MCP 启动路径包含不支持的字符")
        return f"'''{normalized}'''"

    return [
        "--config", f"mcp_servers.feishu_ticket_db.command={toml_literal(sys.executable)}",
        "--config", f"mcp_servers.feishu_ticket_db.args=[{toml_literal(TICKET_MCP_SERVER)}]",
        "--config", "mcp_servers.feishu_ticket_db.enabled=true",
    ]


def _format_error(stderr_text: str) -> str:
    if "Codex cannot access session files" in stderr_text or ".codex/sessions" in stderr_text:
        return (
            "Codex 无法访问 ~/.codex/sessions。请确认 bridge 进程有权限读写本机 "
            "Codex 会话目录，并且这些文件属于当前用户。"
        )
    return stderr_text or "no stderr"


async def _fire_callback(cb, *args):
    if cb is None:
        return
    if asyncio.iscoroutinefunction(cb):
        await cb(*args)
    else:
        cb(*args)


async def run_codex(
    message: str,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    cwd: Optional[str] = None,
    permission_mode: Optional[str] = None,
    images: Optional[list[str]] = None,
    on_text_chunk: Optional[Callable[[str], None]] = None,
    on_tool_use: Optional[Callable[[str, dict], None]] = None,
    on_session_id: Optional[Callable[[str], None]] = None,
    on_process_start: Optional[Callable[[asyncio.subprocess.Process], None]] = None,
) -> tuple[str, Optional[str], bool]:
    """
    Invoke Codex CLI.

    Returns:
        (full_response_text, new_session_id, used_fresh_session_fallback)
    """
    output_fd, output_path = tempfile.mkstemp(prefix="feishu-codex-last-", suffix=".txt")
    os.close(output_fd)

    cmd = [CODEX_CLI, "exec"]
    if session_id:
        cmd += ["resume"]
    cmd += ["--json", "--skip-git-repo-check"]
    cmd += _ticket_mcp_args()
    if session_id:
        cmd += [session_id]
    cmd += ["--output-last-message", output_path]
    cmd += _permission_args(permission_mode, resume=bool(session_id))
    if model:
        cmd += ["-m", model]
    # resume 子命令不支持 -C/--cd；启动进程的 cwd 已在下方单独设置。
    if cwd and not session_id:
        cmd += ["-C", cwd]
    for image in images or []:
        cmd += ["--image", image]
    cmd += ["-"]

    child_env = os.environ.copy()
    child_env["TICKET_DB_CONFIG_DIR"] = TICKET_DB_CONFIG_DIR
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd or os.path.expanduser("~"),
        env=child_env,
        limit=10 * 1024 * 1024,
    )

    await _fire_callback(on_process_start, proc)
    started_at = asyncio.get_running_loop().time()
    last_stdout_at = started_at
    next_wait_log_at = started_at + min(15, IDLE_TIMEOUT)
    _trace_log(f"[Codex 子进程] 已启动 pid={proc.pid}")

    proc.stdin.write((message + "\n").encode())
    await proc.stdin.drain()
    proc.stdin.close()

    full_text = ""
    new_session_id = session_id

    try:
        while True:
            try:
                now = asyncio.get_running_loop().time()
                idle_for = now - last_stdout_at
                remaining = IDLE_TIMEOUT - idle_for
                raw_line = await asyncio.wait_for(
                    proc.stdout.readline(), timeout=min(15, max(0.1, remaining))
                )
            except asyncio.TimeoutError:
                now = asyncio.get_running_loop().time()
                idle_for = now - last_stdout_at
                if idle_for >= IDLE_TIMEOUT:
                    proc.kill()
                    await proc.wait()
                    _trace_log(
                        f"[Codex 子进程] 空闲超时 pid={proc.pid} idle={idle_for:.0f}s，已终止",
                    )
                    raise RuntimeError(f"Codex 执行超时（{IDLE_TIMEOUT}秒无输出），已终止进程")
                if now >= next_wait_log_at:
                    _trace_log(
                        f"[Codex 子进程] 仍在运行 pid={proc.pid} elapsed={now-started_at:.0f}s "
                        f"stdout_idle={idle_for:.0f}s"
                    )
                    next_wait_log_at = now + 15
                continue

            if not raw_line:
                break
            last_stdout_at = asyncio.get_running_loop().time()
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                _trace_log(f"[Codex 子进程] 忽略非 JSON 输出 pid={proc.pid} chars={len(line)}")
                continue

            payload = data.get("payload", data)
            event_type = data.get("type", "unknown")
            item_type = payload.get("type", "") if isinstance(payload, dict) else ""
            _trace_log(
                f"[Codex 事件] pid={proc.pid} type={event_type} item={item_type or '-'}",
            )

            sid = _extract_session_id(data)
            if sid:
                new_session_id = sid
                await _fire_callback(on_session_id, sid)

            tool_call = _extract_tool_call(data)
            if tool_call:
                await _fire_callback(on_tool_use, tool_call[0], tool_call[1])

            chunk = _extract_event_text(data)
            if chunk:
                full_text += chunk
                await _fire_callback(on_text_chunk, chunk)

        stderr_output = await proc.stderr.read()
        await proc.wait()
        stderr_text = stderr_output.decode("utf-8", errors="replace").strip()
        _trace_log(
            f"[Codex 子进程] 退出 pid={proc.pid} code={proc.returncode} "
            f"elapsed={asyncio.get_running_loop().time()-started_at:.1f}s "
            f"stderr_chars={len(stderr_text)}"
        )

        final_text = ""
        try:
            if os.path.exists(output_path):
                with open(output_path, encoding="utf-8", errors="replace") as f:
                    final_text = f.read().strip()
        except OSError:
            final_text = ""
        if final_text:
            full_text = final_text

        if proc.returncode != 0:
            detail = _format_error(stderr_text)
            if full_text:
                return f"{full_text}\n\n[Codex exited with code {proc.returncode}: {detail}]", new_session_id, False
            raise RuntimeError(f"codex exited with code {proc.returncode}: {detail}")

        return full_text.strip(), new_session_id, False
    finally:
        try:
            os.unlink(output_path)
        except OSError:
            pass

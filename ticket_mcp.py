from __future__ import annotations

"""Codex 通过 stdio MCP 使用的票务只读查询工具。"""

from typing import Literal

from mcp.server.fastmcp import FastMCP

from ticket_db import TicketDatabase, safe_tool_call

Environment = Literal["qa", "qad", "prod", "jiushi", "test"]
database = TicketDatabase()
mcp = FastMCP("feishu-ticket-readonly")


@mcp.tool()
def query_show_information(
    environment: Environment,
    acShowId: str | None = None,
    showCode: str | None = None,
    acShowName: str | None = None,
) -> dict:
    """只读查节目。三种条件选一：acShowId 精确 ID、showCode 项目编号、acShowName 模糊节目名。名称多结果时先让用户选节目。"""
    return safe_tool_call(
        "query_show_information", database.query_shows,
        environment, acShowId, showCode, acShowName,
    )


@mcp.tool()
def query_ticket_information(
    environment: Environment,
    ticketNo: str | None = None,
    stockCode: str | None = None,
    realName: str | None = None,
    idNo: str | None = None,
    acShowId: str | None = None,
    acShowName: str | None = None,
    acShowSessionId: str | None = None,
    ticketPrice: float | None = None,
    atTime: str | None = None,
) -> dict:
    """只读查票并计算当前/指定时间能否核验。优先精确 ticketNo 或 stockCode；按姓名须带节目 ID/全称。atTime 为 ISO 本地时间。证件号索引未验证，传 idNo 会安全拒绝，不会猜哈希。"""
    return safe_tool_call(
        "query_ticket_information", database.query_tickets,
        environment, ticketNo, stockCode, realName, idNo, acShowId,
        acShowName, acShowSessionId, ticketPrice, atTime,
    )


@mcp.tool()
def query_ticket_entrances(environment: Environment, ticketNo: str) -> dict:
    """按票号只读查询该票绑定授权码及授权码实际绑定入口；同时列出最近最多 10 条成功核验入口记录。"""
    return safe_tool_call(
        "query_ticket_entrances", database.query_ticket_entrances,
        environment, ticketNo,
    )


@mcp.tool()
def query_verification_rules(
    environment: Environment,
    acShowId: str | None = None,
    seatPlanId: str | None = None,
    acShowSessionId: str | None = None,
    acAuthCode: str | None = None,
    acAuthCodeId: str | None = None,
) -> dict:
    """查询实时票价/授权码核验配置。查询键选一；按节目先用 query_show_information 取得 acShowId。返回核验时间窗和计算后的次数限制，不返回演示规则。"""
    return safe_tool_call(
        "query_verification_rules", database.query_verification_rules,
        environment, acShowId, seatPlanId, acShowSessionId, acAuthCode, acAuthCodeId,
    )


@mcp.tool()
def query_session_seat_plans(
    environment: Environment,
    seatPlanId: str | None = None,
    acShowSessionId: str | None = None,
) -> dict:
    """按 seatPlanId 或 acShowSessionId 二选一查询节目场次的票价、类型、次数限制和核验时间窗。"""
    return safe_tool_call(
        "query_session_seat_plans", database.query_seat_plans,
        environment, seatPlanId, acShowSessionId,
    )


@mcp.tool()
def query_show_entrances(
    environment: Environment,
    acShowId: str | None = None,
    showCode: str | None = None,
) -> dict:
    """按核验节目 ID 或项目编号二选一查询节目下有效入场口；多个节目时先确认节目。"""
    return safe_tool_call(
        "query_show_entrances", database.query_show_entrances,
        environment, acShowId, showCode,
    )


@mcp.tool()
def query_ac_auth_code_information(
    environment: Environment,
    acAuthCode: str | None = None,
    acAuthCodeId: str | None = None,
) -> dict:
    """按授权码或授权码记录 ID 二选一精确查询授权码状态、节目、次数限制和备注。"""
    return safe_tool_call(
        "query_ac_auth_code_information", database.query_auth_code,
        environment, acAuthCode, acAuthCodeId, "information",
    )


@mcp.tool()
def query_ac_auth_code_bindings(
    environment: Environment,
    acAuthCode: str | None = None,
    acAuthCodeId: str | None = None,
) -> dict:
    """按授权码或 ID 二选一，汇总节目内相关场次的全部票价和全部入口，并标记绑定状态及数量。"""
    return safe_tool_call(
        "query_ac_auth_code_bindings", database.query_auth_code,
        environment, acAuthCode, acAuthCodeId, "bindings",
    )


@mcp.tool()
def query_ac_auth_code_bound_seat_plans(
    environment: Environment,
    acAuthCode: str | None = None,
    acAuthCodeId: str | None = None,
) -> dict:
    """按授权码或 ID 二选一查询实际绑定的票价、场次、限制和时间窗。"""
    return safe_tool_call(
        "query_ac_auth_code_bound_seat_plans", database.query_auth_code,
        environment, acAuthCode, acAuthCodeId, "seat_plans",
    )


@mcp.tool()
def query_ac_auth_code_bound_entrances(
    environment: Environment,
    acAuthCode: str | None = None,
    acAuthCodeId: str | None = None,
) -> dict:
    """按授权码或 ID 二选一，只返回授权码实际绑定的有效入口。"""
    return safe_tool_call(
        "query_ac_auth_code_bound_entrances", database.query_auth_code,
        environment, acAuthCode, acAuthCodeId, "entrances",
    )


@mcp.tool()
def query_seat_plan_bound_auth_codes(environment: Environment, seatPlanId: str) -> dict:
    """按 ac_seat_plan.id 反查实际绑定的有效授权码；seatPlanId 不是票价名称或场次 ID。"""
    return safe_tool_call(
        "query_seat_plan_bound_auth_codes", database.query_seat_plan_auth_codes,
        environment, seatPlanId,
    )


if __name__ == "__main__":
    # MCP stdio 协议独占 stdout；不要在该进程使用 print 输出调试信息。
    mcp.run(transport="stdio")

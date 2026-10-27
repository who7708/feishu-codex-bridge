from __future__ import annotations

"""票务只读数据库访问与核验口径。所有 SQL 均为代码内固定语句。"""

from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
import logging
import os
from pathlib import Path
from typing import Any, Iterator, Literal

from dotenv import dotenv_values
import pymysql
from pymysql.cursors import DictCursor

Environment = Literal["qa", "qad", "prod", "jiushi", "test"]

ENV_FILES: dict[str, str] = {
    "qa": ".env.qa.sr",
    "qad": ".env.qad.sr",
    "prod": ".env.prod.sr",
    "jiushi": ".env.jiushi.sr",
    "test": ".env.test",
}
UNLIMITED_SEAT_PLAN_VALUES = {-1, 99, 999}
MAX_ROWS = 20
MAX_CHECK_RECORDS = 10
MAX_AUTH_CODES = 1000
logger = logging.getLogger(__name__)


class ToolInputError(Exception):
    """可安全返回给模型的参数校验错误。"""


def _safe_json(value: Any) -> Any:
    """将 MySQL 返回值转换为 MCP JSON 可序列化类型，不返回二进制字段。"""
    if isinstance(value, dict):
        return {key: _safe_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return "[binary omitted]"
    return value


class TicketDatabase:
    """每个工具调用新建只读事务，环境和密钥始终从同一环境文件读取。"""

    def __init__(self, config_dir: str | None = None):
        self.config_dir = Path(
            config_dir or os.environ.get("TICKET_DB_CONFIG_DIR", os.getcwd())
        ).expanduser().resolve()

    def _config(self, environment: str) -> dict[str, str]:
        file_name = ENV_FILES.get(environment)
        if not file_name:
            raise ValueError("环境只支持 qa、qad、prod、jiushi、test")
        values = dotenv_values(self.config_dir / file_name)
        required = ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")
        if any(not values.get(key) for key in required):
            # 不把路径或配置值返回到 MCP / LLM。
            raise ValueError("目标环境数据库配置不完整")
        return {key: str(value) for key, value in values.items() if value is not None}

    @contextmanager
    def cursor(self, environment: str) -> Iterator[Any]:
        config = self._config(environment)
        try:
            port = int(config["DB_PORT"])
        except (TypeError, ValueError):
            raise ValueError("目标环境数据库配置无效") from None
        connection = pymysql.connect(
            host=config["DB_HOST"],
            port=port,
            user=config["DB_USER"],
            password=config["DB_PASSWORD"],
            database=config["DB_NAME"],
            charset=config.get("DB_CHARSET", "utf8mb4"),
            connect_timeout=5,
            read_timeout=15,
            write_timeout=5,
            cursorclass=DictCursor,
            autocommit=False,
        )
        try:
            with connection.cursor() as cursor:
                # 即使连接账号误有写权限，本次工具事务也只能执行只读 SQL。
                cursor.execute("SET SESSION TRANSACTION READ ONLY")
                yield cursor
        finally:
            connection.rollback()
            connection.close()

    @staticmethod
    def _all(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        cursor.execute(sql, params)
        return [_safe_json(row) for row in cursor.fetchall()]

    @staticmethod
    def _one(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return _safe_json(row) if row else None

    def query_shows(
        self, environment: str, ac_show_id: str | None, show_code: str | None,
        ac_show_name: str | None,
    ) -> dict[str, Any]:
        selectors = [value for value in (ac_show_id, show_code, ac_show_name) if value]
        if len(selectors) != 1:
            return {"error": "请在 acShowId、showCode、acShowName 中提供一个查询条件。"}
        base = """
            SELECT id AS acShowId, ac_show_name AS acShowName,
                   pw_show_id AS pwShowId, pw_show_name AS pwShowName,
                   merchant_id AS merchantId, merchant_name AS merchantName,
                   show_status AS showStatus, venue_id AS venueId, venue_name AS venueName,
                   city_id AS cityId, city_name AS cityName,
                   first_show_time AS firstShowTime, last_show_time AS lastShowTime,
                   check_end_time AS checkEndTime, show_source AS showSource,
                   ac_project_type AS acProjectType, enter_times_limit AS enterTimesLimit
            FROM ac_show
            WHERE COALESCE(is_deleted, 0) = 0
        """
        if ac_show_id:
            sql, params = base + " AND id = %s ORDER BY last_show_time DESC, id DESC LIMIT 21", (ac_show_id,)
        elif show_code:
            sql = base + """
                AND pw_show_id IN (
                    SELECT id FROM std_show
                    WHERE COALESCE(is_deleted, 0) = 0 AND show_code = %s
                )
                ORDER BY last_show_time DESC, id DESC LIMIT 21
            """
            params = (show_code,)
        else:
            sql = base + " AND ac_show_name LIKE %s ORDER BY last_show_time DESC, id DESC LIMIT 21"
            params = (f"%{ac_show_name}%",)
        with self.cursor(environment) as cursor:
            rows = self._all(cursor, sql, params)
        limited = len(rows) > MAX_ROWS
        rows = rows[:MAX_ROWS]
        return {
            "environment": environment,
            "matchedCount": len(rows),
            "selectionRequired": len(rows) > 1,
            "truncated": limited,
            "shows": rows,
        }

    def _resolve_show_name(self, cursor: Any, show_name: str) -> tuple[str | None, dict[str, Any] | None]:
        rows = self._all(cursor, """
            SELECT id AS acShowId, ac_show_name AS acShowName
            FROM ac_show
            WHERE COALESCE(is_deleted, 0) = 0 AND ac_show_name = %s
            ORDER BY id LIMIT 2
        """, (show_name,))
        if not rows:
            return None, {"error": "节目全称未精确匹配到节目，请提供节目 ID。"}
        if len(rows) > 1:
            return None, {"error": "节目全称匹配到多个节目，请提供 acShowId。", "shows": rows}
        return str(rows[0]["acShowId"]), None

    def _ticket_rows(
        self, cursor: Any, ticket_no: str | None, stock_code: str | None,
        real_name: str | None, ac_show_id: str | None, ac_show_name: str | None,
        session_id: str | None, ticket_price: float | None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        identity_selectors = [value for value in (ticket_no, stock_code, real_name) if value]
        if len(identity_selectors) != 1:
            return [], {"error": "请在 ticketNo、stockCode、realName 中提供一个条件。"}
        if ac_show_id and ac_show_name:
            return [], {"error": "节目范围请在 acShowId、acShowName 中提供一个，不要同时传入。"}
        if real_name and not (ac_show_id or ac_show_name):
            return [], {"error": "按姓名查询必须同时提供 acShowId 或 acShowName。"}
        if ac_show_name and not ac_show_id:
            ac_show_id, error = self._resolve_show_name(cursor, ac_show_name)
            if error:
                return [], error

        # id_no_key 的服务端 HashSec 尚未验证，不能用 MD5_SALT 猜测索引值。
        conditions = ["COALESCE(ai.is_deleted, 0) = 0", "COALESCE(ash.is_deleted, 0) = 0"]
        params: list[Any] = []
        for column, value in (("ai.ticket_no", ticket_no), ("ai.stock_code", stock_code),
                              ("ai.real_name", real_name), ("ai.ac_show_id", ac_show_id),
                              ("ai.ac_show_session_id", session_id), ("asp.original_price", ticket_price)):
            if value is not None and value != "":
                conditions.append(f"{column} = %s")
                params.append(value)
        sql = f"""
            SELECT ai.id AS acItemId, ai.ac_show_id AS acShowId,
                   ash.ac_show_name AS acShowName,
                   ai.ac_show_session_id AS acShowSessionId,
                   ass.show_session_name AS acShowSessionName,
                   ai.ac_seat_plan_id AS seatPlanId, asp.seat_plan_name AS seatPlanName,
                   asp.original_price AS ticketPrice, ai.stock_code_ticket_type AS ticketType,
                   ai.stock_order_no AS stockOrderNo, ai.stock_code AS stockCode,
                   ai.stock_code_id AS stockCodeId, ai.ticket_no AS ticketNo,
                   ai.exchange_code AS exchangeCode, ai.ac_status AS sourceStatus,
                   COALESCE(ai.check_times, 0) AS checkTimes,
                   ai.last_check_time AS lastCheckTime,
                   ai.zone_name AS zoneName, ai.sector_name AS sectorName,
                   ai.seat_name AS seatName, ai.invalid_type AS invalidReason,
                   asp.enter_times_limit AS seatPlanLimit,
                   asp.check_start_time AS checkStartTime,
                   asp.check_end_time AS checkEndTime
            FROM ac_item ai
            INNER JOIN ac_show ash ON ash.id = ai.ac_show_id
            LEFT JOIN ac_show_session ass ON ass.id = ai.ac_show_session_id
                AND COALESCE(ass.is_deleted, 0) = 0
            LEFT JOIN ac_seat_plan asp ON asp.id = ai.ac_seat_plan_id
                AND COALESCE(asp.is_deleted, 0) = 0
            WHERE {' AND '.join(conditions)}
            ORDER BY ai.update_time DESC, ai.id DESC LIMIT %s
        """
        params.append(MAX_ROWS + 1)
        rows = self._all(cursor, sql, tuple(params))
        return rows, None

    def _auth_codes_for_seat_plan(self, cursor: Any, seat_plan_id: str | None) -> list[dict[str, Any]]:
        if not seat_plan_id:
            return []
        return self._all(cursor, """
            SELECT DISTINCT code.id AS acAuthCodeId, code.ac_show_id AS acShowId,
                   code.auth_code AS acAuthCode, code.auth_code_status AS status,
                   code.enter_times_limit AS enterTimesLimit, code.remarks AS remarks
            FROM ac_auth_code_bind bind
            INNER JOIN ac_seat_plan asp ON asp.id = bind.bind_object_id
                AND asp.ac_show_id = bind.ac_show_id AND asp.is_deleted = 0
            INNER JOIN ac_auth_code code ON code.id = bind.ac_auth_code_id
                AND code.ac_show_id = bind.ac_show_id AND code.ac_auth_type = 'AUTH_CODE'
                AND code.is_deleted = 0
            WHERE bind.bind_object_type = 'SEAT_PLAN' AND bind.bind_object_id = %s
                AND bind.is_deleted = 0
            ORDER BY code.id LIMIT %s
        """, (seat_plan_id, MAX_AUTH_CODES + 1))

    @staticmethod
    def _effective_limit(seat_plan_limit: Any, auth_codes: list[dict[str, Any]]) -> dict[str, Any]:
        plan_limit = int(seat_plan_limit or 0)
        explicit_limits = sorted({
            int(row["enterTimesLimit"])
            for row in auth_codes
            if row.get("enterTimesLimit") is not None and int(row["enterTimesLimit"]) != -1
        })
        plan_unlimited = plan_limit in UNLIMITED_SEAT_PLAN_VALUES
        if not explicit_limits:
            return {
                "seatPlanLimit": plan_limit,
                "authCodeLimits": [row.get("enterTimesLimit") for row in auth_codes],
                "effectiveLimit": plan_limit,
                "unlimited": plan_unlimited,
                "source": "SEAT_PLAN",
            }
        auth_limit = explicit_limits[0]
        if plan_unlimited:
            effective, source, unlimited = auth_limit, "AUTH_CODE", False
        elif plan_limit < auth_limit:
            effective, source, unlimited = plan_limit, "SEAT_PLAN", False
        elif plan_limit > auth_limit:
            effective, source, unlimited = auth_limit, "AUTH_CODE", False
        else:
            effective, source, unlimited = plan_limit, "SEAT_PLAN_AND_AUTH_CODE", False
        return {
            "seatPlanLimit": plan_limit,
            "authCodeLimits": [row.get("enterTimesLimit") for row in auth_codes],
            "effectiveLimit": effective,
            "unlimited": unlimited,
            "source": source,
        }

    @staticmethod
    def _evaluate_ticket(ticket: dict[str, Any], effective: dict[str, Any], at_time: datetime) -> dict[str, Any]:
        check_times = int(ticket.get("checkTimes") or 0)
        limit = int(effective["effectiveLimit"])
        unlimited = bool(effective["unlimited"])
        remaining = None if unlimited else limit - check_times
        status = ticket.get("sourceStatus")
        invalid = status in (2, "2", "INVALID")
        start = ticket.get("checkStartTime")
        end = ticket.get("checkEndTime")
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        if isinstance(end, str):
            end = datetime.fromisoformat(end)
        if invalid:
            can_verify, state, reason = False, "INVALID", "票务明细已失效。"
        elif not unlimited and remaining is not None and remaining <= 0:
            can_verify, state, reason = False, "CHECK_TIMES_EXHAUSTED", "有效核验次数已用完。"
        elif not start or not end:
            can_verify, state, reason = False, "RULE_DATA_MISSING", "票价未配置完整核验时间窗，无法判断。"
        elif at_time < start:
            can_verify, state, reason = False, "NOT_STARTED", "尚未到达核验开始时间。"
        elif at_time > end:
            can_verify, state, reason = False, "EXPIRED", "已超过核验结束时间。"
        else:
            can_verify = True
            state = "VERIFIABLE_REENTRY" if check_times > 0 else "VERIFIABLE_FIRST_ENTRY"
            reason = "核验次数无上限，且当前时间在核验窗口内。" if unlimited else "次数和核验时间窗均符合规则。"
        if invalid:
            status_name = "INVALID"
        elif check_times <= 0:
            status_name = "WAIT_CHECK"
        elif unlimited or check_times < limit:
            status_name = "PARTIALLY_CHECKED"
        else:
            status_name = "CHECKED"
        return {
            "acStatus": status_name,
            "checkTimes": check_times,
            "checkTimesLimit": limit,
            "checkTimesLimitSource": effective["source"],
            "checkTimesUnlimited": unlimited,
            "remainingCheckTimes": remaining,
            "canVerify": can_verify,
            "verificationState": state,
            "verificationReason": reason,
            "evaluationTime": at_time.isoformat(sep=" "),
            "checkStartTime": _safe_json(ticket.get("checkStartTime")),
            "checkEndTime": _safe_json(ticket.get("checkEndTime")),
        }

    @staticmethod
    def _parse_evaluation_time(value: str | None) -> datetime:
        if not value:
            return datetime.now()
        try:
            result = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ToolInputError("atTime 必须使用 ISO-8601 本地时间，例如 2026-08-01T18:30:00") from exc
        if result.tzinfo is not None:
            raise ToolInputError("atTime 使用本地时间，不接受时区偏移")
        return result

    def query_tickets(
        self, environment: str, ticket_no: str | None, stock_code: str | None,
        real_name: str | None, id_no: str | None, ac_show_id: str | None,
        ac_show_name: str | None, session_id: str | None, ticket_price: float | None,
        at_time: str | None,
    ) -> dict[str, Any]:
        if id_no:
            if ticket_no or stock_code or real_name:
                return {"error": "请只提供 ticketNo、stockCode、realName、idNo 中的一种查询条件。"}
            return {"error": "证件号索引算法尚未与服务端 HashSec 验证，暂不按证件号查询。请改用票号、票码，或提供实名和节目条件。"}
        evaluation_time = self._parse_evaluation_time(at_time)
        with self.cursor(environment) as cursor:
            tickets, error = self._ticket_rows(
                cursor, ticket_no, stock_code, real_name, ac_show_id,
                ac_show_name, session_id, ticket_price,
            )
            if error:
                return error
            truncated = len(tickets) > MAX_ROWS
            tickets = tickets[:MAX_ROWS]
            results = []
            for ticket in tickets:
                auth_codes = self._auth_codes_for_seat_plan(cursor, ticket.get("seatPlanId"))
                if len(auth_codes) > MAX_AUTH_CODES:
                    return {"error": "授权码绑定超过安全处理上限，未计算可能不完整的核验结论。"}
                effective = self._effective_limit(ticket.get("seatPlanLimit"), auth_codes)
                decision = self._evaluate_ticket(ticket, effective, evaluation_time)
                check_records = self._check_records(cursor, str(ticket["acItemId"]))
                results.append({
                    key: ticket.get(key)
                    for key in (
                        "acItemId", "acShowId", "acShowName", "acShowSessionId",
                        "acShowSessionName", "seatPlanId", "seatPlanName", "ticketPrice",
                        "ticketType", "stockOrderNo", "stockCode", "stockCodeId", "ticketNo",
                        "exchangeCode", "lastCheckTime", "zoneName", "sectorName", "seatName",
                        "invalidReason",
                    )
                } | decision | {
                    "authCodes": [
                        {key: row.get(key) for key in (
                            "acAuthCodeId", "acAuthCode", "status", "enterTimesLimit", "remarks"
                        )}
                        for row in auth_codes[:MAX_ROWS]
                    ],
                    "authCodesTruncated": len(auth_codes) > MAX_ROWS,
                    "checkRecords": check_records["records"],
                    "checkRecordLimitExceeded": check_records["limitExceeded"],
                })
        return {
            "environment": environment,
            "matchedCount": len(results),
            "truncated": truncated,
            "evaluationTime": evaluation_time.isoformat(sep=" "),
            "tickets": results,
            "identityQueryNote": "证件号查询仅在服务端 HashSec 算法确认后开放。",
        }

    def _check_records(self, cursor: Any, ac_item_id: str) -> dict[str, Any]:
        rows = self._all(cursor, """
            SELECT ail.operation_time AS checkTime,
                   COALESCE(NULLIF(ase.entrance_name, ''), ail.entrance_name) AS entranceName,
                   ase.entrance_method AS entranceMethod,
                   ase.entrance_desc AS entranceDescription,
                   ad.venue_name AS venueName,
                   COALESCE(NULLIF(ad.device_name, ''), ail.device_name) AS deviceName,
                   COALESCE(NULLIF(ad.device_number, ''), ail.device_number) AS deviceNumber,
                   ail.check_type AS checkType, ail.check_device_type AS checkDeviceType
            FROM ac_item_log ail
            LEFT JOIN ac_show_entrance ase ON ase.id = ail.ac_show_entrance_id
                AND COALESCE(ase.is_deleted, 0) = 0
            LEFT JOIN ac_device ad ON ad.id = ail.device_id
                AND COALESCE(ad.is_deleted, 0) = 0
            WHERE ail.ac_item_id = %s AND COALESCE(ail.is_deleted, 0) = 0
                AND ail.admission_status = 'PASSED'
                AND ail.operation_type = 'ADMISSION_CHECK'
                AND COALESCE(ail.canceled, 0) = 0
                AND COALESCE(ail.is_visible, 1) = 1
            ORDER BY ail.operation_time DESC, ail.id DESC LIMIT %s
        """, (ac_item_id, MAX_CHECK_RECORDS + 1))
        return {"records": rows[:MAX_CHECK_RECORDS], "limitExceeded": len(rows) > MAX_CHECK_RECORDS}

    def _authorization(
        self, cursor: Any, auth_code: str | None, auth_code_id: str | None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if bool(auth_code) == bool(auth_code_id):
            return None, {"error": "请在 acAuthCode、acAuthCodeId 中提供一个条件。"}
        column, value = ("id", auth_code_id) if auth_code_id else ("auth_code", auth_code)
        row_sql = f"""
            SELECT id AS acAuthCodeId, ac_show_id AS acShowId,
                   auth_code AS acAuthCode, auth_code_status AS status,
                   enter_times_limit AS enterTimesLimit, remarks
            FROM ac_auth_code
            WHERE ac_auth_type = 'AUTH_CODE' AND is_deleted = 0
                AND {column} = %s
            ORDER BY id LIMIT 2
        """
        rows = self._all(cursor, row_sql, (value,))
        if not rows:
            return None, {"found": False, "message": "未找到有效授权码。"}
        if len(rows) > 1:
            return None, {"error": "授权码匹配到多条记录，请使用 acAuthCodeId。"}
        return rows[0], None

    def _bound_seat_plans(self, cursor: Any, auth_code_id: str) -> list[dict[str, Any]]:
        return self._all(cursor, """
            SELECT DISTINCT asp.ac_show_id AS acShowId,
                   asp.ac_show_session_id AS acShowSessionId,
                   ass.show_session_name AS showSessionName,
                   asp.id AS seatPlanId, asp.seat_plan_type AS seatPlanType,
                   asp.seat_plan_name AS seatPlanName,
                   asp.enter_times_limit AS enterTimesLimit,
                   asp.check_start_time AS checkStartTime,
                   asp.check_end_time AS checkEndTime
            FROM ac_auth_code_bind bind
            INNER JOIN ac_seat_plan asp ON asp.id = bind.bind_object_id
                AND asp.ac_show_id = bind.ac_show_id AND asp.is_deleted = 0
            LEFT JOIN ac_show_session ass ON ass.id = asp.ac_show_session_id
                AND ass.ac_show_id = asp.ac_show_id AND ass.is_deleted = 0
            WHERE bind.ac_auth_code_id = %s AND bind.bind_object_type = 'SEAT_PLAN'
                AND bind.is_deleted = 0
            ORDER BY asp.ac_show_session_id, asp.id LIMIT %s
        """, (auth_code_id, MAX_AUTH_CODES + 1))

    def _bound_entrances(self, cursor: Any, auth_code_id: str) -> list[dict[str, Any]]:
        return self._all(cursor, """
            SELECT DISTINCT ase.ac_show_id AS acShowId,
                   ash.ac_show_name AS acShowName,
                   ase.id AS entranceId, ase.entrance_name AS entranceName
            FROM ac_auth_code_bind bind
            INNER JOIN ac_show_entrance ase ON ase.id = bind.bind_object_id
                AND ase.ac_show_id = bind.ac_show_id AND ase.is_deleted = 0
            LEFT JOIN ac_show ash ON ash.id = ase.ac_show_id AND COALESCE(ash.is_deleted, 0) = 0
            WHERE bind.ac_auth_code_id = %s AND bind.bind_object_type = 'AC_ENTRANCE'
                AND bind.is_deleted = 0
            ORDER BY ase.id LIMIT %s
        """, (auth_code_id, MAX_AUTH_CODES + 1))

    def _seat_plans_for_sessions(self, cursor: Any, session_ids: list[str]) -> list[dict[str, Any]]:
        if not session_ids:
            return []
        marks = ",".join("%s" for _ in session_ids)
        return self._all(cursor, f"""
            SELECT asp.ac_show_id AS acShowId,
                   asp.ac_show_session_id AS acShowSessionId,
                   ass.show_session_name AS showSessionName,
                   asp.id AS seatPlanId, asp.seat_plan_type AS seatPlanType,
                   asp.seat_plan_name AS seatPlanName,
                   asp.enter_times_limit AS enterTimesLimit,
                   asp.check_start_time AS checkStartTime,
                   asp.check_end_time AS checkEndTime
            FROM ac_seat_plan asp
            LEFT JOIN ac_show_session ass ON ass.id = asp.ac_show_session_id
                AND ass.ac_show_id = asp.ac_show_id AND ass.is_deleted = 0
            WHERE asp.is_deleted = 0
                AND asp.ac_show_session_id IN ({marks})
            ORDER BY asp.ac_show_session_id, asp.id LIMIT %s
        """, tuple(session_ids) + (MAX_ROWS + 1,))

    def _show_entrances(self, cursor: Any, show_id: str) -> list[dict[str, Any]]:
        return self._all(cursor, """
            SELECT ase.ac_show_id AS acShowId, ash.ac_show_name AS acShowName,
                   ase.id AS entranceId, ase.entrance_name AS entranceName
            FROM ac_show_entrance ase
            LEFT JOIN ac_show ash ON ash.id = ase.ac_show_id AND COALESCE(ash.is_deleted, 0) = 0
            WHERE ase.is_deleted = 0 AND ase.ac_show_id = %s
            ORDER BY ase.id LIMIT %s
        """, (show_id, MAX_ROWS + 1))

    def _ticket_entrances(self, cursor: Any, ticket_no: str) -> dict[str, Any]:
        tickets, error = self._ticket_rows(cursor, ticket_no, None, None, None, None, None, None)
        if error:
            return error
        truncated = len(tickets) > MAX_ROWS
        results = []
        for ticket in tickets[:MAX_ROWS]:
            auth_codes = self._auth_codes_for_seat_plan(cursor, ticket.get("seatPlanId"))
            if len(auth_codes) > MAX_AUTH_CODES:
                return {"error": "授权码绑定超过安全处理上限，未生成可能不完整的入口结果。"}
            authorizations = []
            for reference in auth_codes:
                auth, error = self._authorization(cursor, None, str(reference["acAuthCodeId"]))
                if not auth or error:
                    continue
                authorizations.append({"authCode": auth, "entrances": self._bound_entrances(cursor, str(auth["acAuthCodeId"]))})
            checks = self._check_records(cursor, str(ticket["acItemId"]))
            results.append({
                "ticketNo": ticket.get("ticketNo"),
                "stockCode": ticket.get("stockCode"),
                "acShowId": ticket.get("acShowId"),
                "acShowName": ticket.get("acShowName"),
                "seatPlanId": ticket.get("seatPlanId"),
                "seatPlanName": ticket.get("seatPlanName"),
                "checkTimes": ticket.get("checkTimes"),
                "checkStartTime": ticket.get("checkStartTime"),
                "checkEndTime": ticket.get("checkEndTime"),
                "authorizations": authorizations,
                "historicalSuccessfulEntrances": checks["records"],
                "checkRecordLimitExceeded": checks["limitExceeded"],
            })
        return {"tickets": results, "matchedCount": len(results), "truncated": truncated}

    def query_ticket_entrances(self, environment: str, ticket_no: str) -> dict[str, Any]:
        if not ticket_no:
            return {"error": "ticketNo 不能为空。"}
        with self.cursor(environment) as cursor:
            return {"environment": environment, **self._ticket_entrances(cursor, ticket_no)}

    def query_auth_code(
        self, environment: str, auth_code: str | None, auth_code_id: str | None,
        detail: str,
    ) -> dict[str, Any]:
        with self.cursor(environment) as cursor:
            auth, error = self._authorization(cursor, auth_code, auth_code_id)
            if error:
                return error
            if detail == "information":
                return {"environment": environment, "found": True, "authorization": auth}
            seat_plans = self._bound_seat_plans(cursor, str(auth["acAuthCodeId"]))
            entrances = self._bound_entrances(cursor, str(auth["acAuthCodeId"]))
            if len(seat_plans) > MAX_AUTH_CODES or len(entrances) > MAX_AUTH_CODES:
                return {"error": "授权码绑定超过安全处理上限，未生成可能不完整的结果。"}
            if detail == "seat_plans":
                return {
                    "environment": environment, "authorization": auth,
                    "seatPlans": seat_plans[:MAX_ROWS], "truncated": len(seat_plans) > MAX_ROWS,
                }
            if detail == "entrances":
                return {
                    "environment": environment, "authorization": auth,
                    "entrances": entrances[:MAX_ROWS], "truncated": len(entrances) > MAX_ROWS,
                }

            session_ids = list(dict.fromkeys(
                str(row["acShowSessionId"]) for row in seat_plans if row.get("acShowSessionId")
            ))
            all_plans = self._seat_plans_for_sessions(cursor, session_ids)
            all_entrances = self._show_entrances(cursor, str(auth["acShowId"]))
            bound_plan_ids = {str(row["seatPlanId"]) for row in seat_plans}
            bound_entrance_ids = {str(row["entranceId"]) for row in entrances}
            for row in all_plans:
                row["isBound"] = str(row["seatPlanId"]) in bound_plan_ids
            for row in all_entrances:
                row["isBound"] = str(row["entranceId"]) in bound_entrance_ids
            return {
                "environment": environment,
                "authorization": auth,
                "seatPlans": all_plans[:MAX_ROWS],
                "seatPlansTruncated": len(all_plans) > MAX_ROWS,
                "entrances": all_entrances[:MAX_ROWS],
                "entrancesTruncated": len(all_entrances) > MAX_ROWS,
                "summary": {
                    "returnedBoundSeatPlans": sum(row["isBound"] for row in all_plans[:MAX_ROWS]),
                    "returnedUnboundSeatPlans": sum(not row["isBound"] for row in all_plans[:MAX_ROWS]),
                    "returnedBoundEntrances": sum(row["isBound"] for row in all_entrances[:MAX_ROWS]),
                    "returnedUnboundEntrances": sum(not row["isBound"] for row in all_entrances[:MAX_ROWS]),
                    "countsDescribeReturnedRowsOnly": True,
                },
            }

    def query_show_entrances(
        self, environment: str, ac_show_id: str | None, show_code: str | None,
    ) -> dict[str, Any]:
        if bool(ac_show_id) == bool(show_code):
            return {"error": "请在 acShowId、showCode 中提供一个条件。"}
        with self.cursor(environment) as cursor:
            shows = [{"acShowId": ac_show_id}] if ac_show_id else self._all(cursor, """
                    SELECT ash.id AS acShowId, ash.ac_show_name AS acShowName FROM ac_show ash
                    WHERE COALESCE(ash.is_deleted, 0) = 0 AND ash.pw_show_id IN (
                        SELECT id FROM std_show WHERE COALESCE(is_deleted, 0) = 0 AND show_code = %s
                    ) ORDER BY ash.id LIMIT %s
                """, (show_code, MAX_ROWS + 1))
            show_ids = [str(row["acShowId"]) for row in shows]
            if len(show_ids) > 1:
                return {
                    "environment": environment,
                    "matchedShowCount": min(len(show_ids), MAX_ROWS),
                    "selectionRequired": True,
                    "truncated": len(show_ids) > MAX_ROWS,
                    "shows": shows[:MAX_ROWS],
                }
            entrances = []
            for show_id in show_ids[:MAX_ROWS]:
                entrances.extend(self._show_entrances(cursor, str(show_id)))
            return {
                "environment": environment,
                "matchedShowCount": len(show_ids),
                "selectionRequired": len(show_ids) > 1,
                "truncated": len(show_ids) > MAX_ROWS or len(entrances) > MAX_ROWS,
                "entrances": entrances[:MAX_ROWS],
            }

    def query_seat_plans(
        self, environment: str, seat_plan_id: str | None, session_id: str | None,
    ) -> dict[str, Any]:
        if bool(seat_plan_id) == bool(session_id):
            return {"error": "请在 seatPlanId、acShowSessionId 中提供一个条件。"}
        with self.cursor(environment) as cursor:
            if seat_plan_id:
                rows = self._all(cursor, """
                    SELECT asp.ac_show_id AS acShowId,
                           asp.ac_show_session_id AS acShowSessionId,
                           ass.show_session_name AS showSessionName,
                           asp.id AS seatPlanId, asp.seat_plan_type AS seatPlanType,
                           asp.seat_plan_name AS seatPlanName,
                           asp.enter_times_limit AS enterTimesLimit,
                           asp.check_start_time AS checkStartTime,
                           asp.check_end_time AS checkEndTime
                    FROM ac_seat_plan asp LEFT JOIN ac_show_session ass
                        ON ass.id = asp.ac_show_session_id AND ass.ac_show_id = asp.ac_show_id
                        AND ass.is_deleted = 0
                    WHERE asp.is_deleted = 0 AND asp.id = %s LIMIT 21
                """, (seat_plan_id,))
            else:
                rows = self._all(cursor, """
                    SELECT asp.ac_show_id AS acShowId,
                           asp.ac_show_session_id AS acShowSessionId,
                           ass.show_session_name AS showSessionName,
                           asp.id AS seatPlanId, asp.seat_plan_type AS seatPlanType,
                           asp.seat_plan_name AS seatPlanName,
                           asp.enter_times_limit AS enterTimesLimit,
                           asp.check_start_time AS checkStartTime,
                           asp.check_end_time AS checkEndTime
                    FROM ac_seat_plan asp LEFT JOIN ac_show_session ass
                        ON ass.id = asp.ac_show_session_id AND ass.ac_show_id = asp.ac_show_id
                        AND ass.is_deleted = 0
                    WHERE asp.is_deleted = 0
                        AND asp.ac_show_session_id = %s
                    ORDER BY asp.id LIMIT 21
                """, (session_id,))
        return {
            "environment": environment,
            "matchedCount": min(len(rows), MAX_ROWS),
            "truncated": len(rows) > MAX_ROWS,
            "seatPlans": rows[:MAX_ROWS],
        }

    def query_verification_rules(
        self, environment: str, ac_show_id: str | None, seat_plan_id: str | None,
        session_id: str | None, auth_code: str | None, auth_code_id: str | None,
    ) -> dict[str, Any]:
        selectors = [value for value in (ac_show_id, seat_plan_id, session_id, auth_code, auth_code_id) if value]
        if len(selectors) != 1:
            return {"error": "请提供 acShowId、seatPlanId、acShowSessionId、acAuthCode 或 acAuthCodeId 中的一个。"}
        if auth_code or auth_code_id:
            result = self.query_auth_code(environment, auth_code, auth_code_id, "seat_plans")
            if result.get("error"):
                return result
            auth = result["authorization"]
            plans = result["seatPlans"]
            return {
                "environment": environment,
                "source": "SR 数据库 ac_seat_plan + ac_auth_code_bind",
                "authorization": auth,
                "rules": [self._rule_summary(plan, [auth]) for plan in plans],
                "truncated": result.get("truncated", False),
                "note": "时间窗来自票价；SR 中没有独立 ac_check_rule 表，星期/入口条件不在本查询结论内。",
            }
        with self.cursor(environment) as cursor:
            if ac_show_id:
                plans = self._all(cursor, """
                    SELECT asp.ac_show_id AS acShowId,
                           asp.ac_show_session_id AS acShowSessionId,
                           ass.show_session_name AS showSessionName,
                           asp.id AS seatPlanId, asp.seat_plan_type AS seatPlanType,
                           asp.seat_plan_name AS seatPlanName,
                           asp.enter_times_limit AS enterTimesLimit,
                           asp.check_start_time AS checkStartTime,
                           asp.check_end_time AS checkEndTime
                    FROM ac_seat_plan asp LEFT JOIN ac_show_session ass
                        ON ass.id = asp.ac_show_session_id AND ass.ac_show_id = asp.ac_show_id
                        AND ass.is_deleted = 0
                    WHERE asp.is_deleted = 0 AND asp.ac_show_id = %s
                    ORDER BY asp.ac_show_session_id, asp.id LIMIT %s
                """, (ac_show_id, MAX_ROWS + 1))
            elif seat_plan_id:
                plans = self._all(cursor, """
                    SELECT asp.ac_show_id AS acShowId,
                           asp.ac_show_session_id AS acShowSessionId,
                           ass.show_session_name AS showSessionName,
                           asp.id AS seatPlanId, asp.seat_plan_type AS seatPlanType,
                           asp.seat_plan_name AS seatPlanName,
                           asp.enter_times_limit AS enterTimesLimit,
                           asp.check_start_time AS checkStartTime,
                           asp.check_end_time AS checkEndTime
                    FROM ac_seat_plan asp LEFT JOIN ac_show_session ass
                        ON ass.id = asp.ac_show_session_id AND ass.ac_show_id = asp.ac_show_id
                        AND ass.is_deleted = 0
                    WHERE asp.is_deleted = 0 AND asp.id = %s LIMIT 2
                """, (seat_plan_id,))
            else:
                plans = self._seat_plans_for_sessions(cursor, [session_id])
            truncated = len(plans) > MAX_ROWS
            plans = plans[:MAX_ROWS]
            rules = []
            for plan in plans:
                auth_codes = self._auth_codes_for_seat_plan(cursor, str(plan["seatPlanId"]))
                if len(auth_codes) > MAX_AUTH_CODES:
                    return {"error": "授权码绑定超过安全处理上限，未计算可能不完整的核验规则。"}
                rules.append(self._rule_summary(plan, auth_codes))
        return {
            "environment": environment,
            "source": "SR 数据库 ac_seat_plan + ac_auth_code_bind",
            "acShowId": ac_show_id,
            "rules": rules,
            "truncated": truncated,
            "note": "时间窗来自票价；SR 中没有独立 ac_check_rule 表，星期/入口条件不在本查询结论内。",
        }

    @staticmethod
    def _rule_summary(plan: dict[str, Any], auth_codes: list[dict[str, Any]]) -> dict[str, Any]:
        plan_limit = plan.get("enterTimesLimit")
        effective = TicketDatabase._effective_limit(plan_limit, auth_codes)
        return {
            "acShowId": plan.get("acShowId"),
            "acShowSessionId": plan.get("acShowSessionId"),
            "showSessionName": plan.get("showSessionName"),
            "seatPlanId": plan.get("seatPlanId"),
            "seatPlanName": plan.get("seatPlanName"),
            "seatPlanType": plan.get("seatPlanType"),
            "checkStartTime": plan.get("checkStartTime"),
            "checkEndTime": plan.get("checkEndTime"),
            "seatPlanEnterTimesLimit": plan_limit,
            "authCodeEnterTimesLimits": effective["authCodeLimits"],
            "effectiveEnterTimesLimit": effective["effectiveLimit"],
            "unlimited": effective["unlimited"],
            "limitSource": effective["source"],
        }

    def query_seat_plan_auth_codes(self, environment: str, seat_plan_id: str) -> dict[str, Any]:
        if not seat_plan_id:
            return {"error": "seatPlanId 不能为空。"}
        with self.cursor(environment) as cursor:
            rows = self._all(cursor, """
                SELECT DISTINCT code.id AS acAuthCodeId, code.auth_code AS acAuthCode,
                       code.auth_code_status AS status, code.enter_times_limit AS enterTimesLimit,
                       code.remarks AS remarks
                FROM ac_auth_code_bind bind
                INNER JOIN ac_seat_plan asp ON asp.id = bind.bind_object_id
                    AND asp.ac_show_id = bind.ac_show_id AND asp.is_deleted = 0
                INNER JOIN ac_auth_code code ON code.id = bind.ac_auth_code_id
                    AND code.ac_show_id = bind.ac_show_id AND code.ac_auth_type = 'AUTH_CODE'
                    AND code.is_deleted = 0
                WHERE bind.bind_object_type = 'SEAT_PLAN' AND bind.bind_object_id = %s
                    AND bind.is_deleted = 0
                ORDER BY code.id LIMIT %s
            """, (seat_plan_id, MAX_ROWS + 1))
        return {
            "environment": environment,
            "seatPlanId": seat_plan_id,
            "matchedCount": min(len(rows), MAX_ROWS),
            "truncated": len(rows) > MAX_ROWS,
            "authCodes": rows[:MAX_ROWS],
        }


def safe_tool_call(tool_name: str, operation, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """屏蔽配置路径、连接串、证件号和驱动异常细节，避免泄露到飞书。"""
    try:
        return operation(*args, **kwargs)
    except ToolInputError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # SQL/连接错误可能包含驱动细节或敏感配置，不能原样回传。
        logger.error("票务工具失败: tool=%s errorType=%s", tool_name, type(exc).__name__)
        return {"error": "查询失败，请检查目标环境配置或数据库连接。未返回任何连接或密钥信息。"}


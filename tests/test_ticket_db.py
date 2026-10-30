from datetime import datetime
from contextlib import contextmanager

from ticket_db import ENV_FILES, TicketDatabase, safe_tool_call


def test_environment_files_are_explicit_and_separate():
    assert ENV_FILES == {
        "qa": ".env.qa.sr",
        "qad": ".env.qad.sr",
        "prod": ".env.prod.sr",
        "jiushi": ".env.jiushi.sr",
        "test": ".env.test",
    }


def test_effective_limit_inherits_auth_code_minus_one():
    result = TicketDatabase._effective_limit(3, [{"enterTimesLimit": -1}])
    assert result == {
        "seatPlanLimit": 3,
        "authCodeLimits": [-1],
        "effectiveLimit": 3,
        "unlimited": False,
        "source": "SEAT_PLAN",
    }


def test_effective_limit_uses_tightest_explicit_auth_code_limit():
    result = TicketDatabase._effective_limit(5, [
        {"enterTimesLimit": 4}, {"enterTimesLimit": 2}, {"enterTimesLimit": -1},
    ])
    assert result["effectiveLimit"] == 2
    assert result["source"] == "AUTH_CODE"


def test_unlimited_seat_plan_can_be_limited_by_auth_code():
    result = TicketDatabase._effective_limit(99, [{"enterTimesLimit": 4}])
    assert result["effectiveLimit"] == 4
    assert result["unlimited"] is False
    assert result["source"] == "AUTH_CODE"


def test_rule_summary_combines_all_bound_auth_code_limits():
    rule = TicketDatabase._rule_summary(
        {
            "seatPlanId": "seat-1",
            "enterTimesLimit": 5,
            "checkStartTime": "2026-08-01 18:00:00",
            "checkEndTime": "2026-08-01 20:00:00",
        },
        [{"enterTimesLimit": 4}, {"enterTimesLimit": 2}, {"enterTimesLimit": -1}],
    )
    assert rule["effectiveEnterTimesLimit"] == 2
    assert rule["limitSource"] == "AUTH_CODE"
    assert rule["authCodeEnterTimesLimits"] == [4, 2, -1]


def test_ticket_is_verifiable_on_inclusive_time_boundaries():
    now = datetime(2026, 8, 1, 18, 30)
    ticket = {
        "sourceStatus": 0,
        "checkTimes": 0,
        "checkStartTime": "2026-08-01 18:30:00",
        "checkEndTime": "2026-08-01 19:30:00",
    }
    decision = TicketDatabase._evaluate_ticket(
        ticket,
        {"effectiveLimit": 2, "unlimited": False, "source": "SEAT_PLAN"},
        now,
    )
    assert decision["canVerify"] is True
    assert decision["verificationState"] == "VERIFIABLE_FIRST_ENTRY"


def test_exhausted_ticket_fails_before_time_window_check():
    ticket = {
        "sourceStatus": 0,
        "checkTimes": 2,
        "checkStartTime": None,
        "checkEndTime": None,
    }
    decision = TicketDatabase._evaluate_ticket(
        ticket,
        {"effectiveLimit": 2, "unlimited": False, "source": "SEAT_PLAN"},
        datetime(2026, 8, 1, 18, 30),
    )
    assert decision["canVerify"] is False
    assert decision["verificationState"] == "CHECK_TIMES_EXHAUSTED"


def test_expired_ticket_fails_after_window():
    ticket = {
        "sourceStatus": 0,
        "checkTimes": 0,
        "checkStartTime": "2026-08-01 18:30:00",
        "checkEndTime": "2026-08-01 19:30:00",
    }
    decision = TicketDatabase._evaluate_ticket(
        ticket,
        {"effectiveLimit": 2, "unlimited": False, "source": "SEAT_PLAN"},
        datetime(2026, 8, 1, 19, 30, 1),
    )
    assert decision["canVerify"] is False
    assert decision["verificationState"] == "EXPIRED"


def test_invalid_ticket_fails_even_when_time_window_is_open():
    ticket = {
        "sourceStatus": 2,
        "checkTimes": 0,
        "checkStartTime": "2026-08-01 18:00:00",
        "checkEndTime": "2026-08-01 20:00:00",
    }
    decision = TicketDatabase._evaluate_ticket(
        ticket,
        {"effectiveLimit": 2, "unlimited": False, "source": "SEAT_PLAN"},
        datetime(2026, 8, 1, 19, 0),
    )
    assert decision["canVerify"] is False
    assert decision["verificationState"] == "INVALID"


def test_id_number_lookup_encrypts_for_environment_and_binds_id_no(monkeypatch):
    database = TicketDatabase("not-read")
    captured = {}

    def encrypt_id_no(environment, id_no):
        captured["crypto_environment"] = environment
        captured["plain_id_no"] = id_no
        return "enc1_test_ciphertext"

    class Cursor:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params

        def fetchall(self):
            return []

    @contextmanager
    def fake_cursor(environment):
        captured["database_environment"] = environment
        yield Cursor()

    monkeypatch.setattr(database, "_encrypt_id_no", encrypt_id_no)
    monkeypatch.setattr(database, "cursor", fake_cursor)
    result = database.query_tickets(
        "qa", None, None, None, "private-id", None, None, None, None, None,
    )
    assert captured["crypto_environment"] == captured["database_environment"] == "qa"
    assert captured["plain_id_no"] == "private-id"
    assert "ai.id_no = %s" in captured["sql"]
    assert "enc1_test_ciphertext" in captured["params"]
    assert result["matchedCount"] == 0


def test_tool_error_response_does_not_expose_exception_details():
    result = safe_tool_call("test_tool", lambda: (_ for _ in ()).throw(RuntimeError("password=secret")))
    assert result == {"error": "查询失败，请检查目标环境配置或数据库连接。未返回任何连接或密钥信息。"}
    assert "secret" not in str(result)


def test_show_name_is_bound_as_sql_parameter(monkeypatch):
    database = TicketDatabase("not-read")
    captured = {}

    class Cursor:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params

        def fetchall(self):
            return []

    @contextmanager
    def fake_cursor(_environment):
        yield Cursor()

    monkeypatch.setattr(database, "cursor", fake_cursor)
    result = database.query_shows("qa", None, None, "票名%' OR 1=1 --")

    assert result["shows"] == []
    assert "票名%' OR 1=1 --" not in captured["sql"]
    assert captured["params"] == ("%票名%' OR 1=1 --%",)


def test_database_transaction_is_read_only(monkeypatch, tmp_path):
    env_file = tmp_path / ".env.qa.sr"
    env_file.write_text(
        "DB_HOST=db.invalid\nDB_PORT=3306\nDB_USER=reader\n"
        "DB_PASSWORD=not-a-real-password\nDB_NAME=ticket\n",
        encoding="utf-8",
    )
    statements = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql):
            statements.append(sql)

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def rollback(self):
            statements.append("ROLLBACK")

        def close(self):
            statements.append("CLOSE")

    monkeypatch.setattr("ticket_db.pymysql.connect", lambda **_kwargs: FakeConnection())
    database = TicketDatabase(str(tmp_path))
    with database.cursor("qa"):
        pass

    assert statements == ["SET SESSION TRANSACTION READ ONLY", "ROLLBACK", "CLOSE"]

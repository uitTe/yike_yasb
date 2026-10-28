"""使用本机真实会话验证续接文件统计，全部快照保存在测试目录。"""

import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from shutil import copyfile

import pytest

from core.widgets.services.codex_usage.codex_api import _TOKEN_FILE_CACHE, _codex_home, read_local_token_usage


def test_real_session_continuations_and_duplicate_files(tmp_path):
    home = _codex_home()
    snapshots = []
    daily_endpoints = defaultdict(dict)
    file_totals = 0
    session_files = defaultdict(int)
    for directory in ("sessions", "archived_sessions"):
        for index, source in enumerate((home / directory).rglob("*.jsonl")):
            snapshot = tmp_path / directory / f"{index}.jsonl"
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            copyfile(source, snapshot)
            snapshots.append(snapshot)
            session_id = None
            final_total = 0
            for line in snapshot.read_text(encoding="utf-8").splitlines():
                if '"session_meta"' not in line and '"token_count"' not in line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                payload = event.get("payload", {})
                if event.get("type") == "session_meta":
                    session_id = payload["id"]
                if event.get("type") != "event_msg" or payload.get("type") != "token_count":
                    continue
                usage = (payload.get("info") or {}).get("total_token_usage")
                if not usage:
                    continue
                day = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).astimezone().date()
                final_total = usage["total_tokens"]
                daily_endpoints[session_id][day] = max(daily_endpoints[session_id].get(day, 0), final_total)
            if final_total:
                session_files[session_id] += 1
                file_totals += final_total

    if not any(count > 1 for count in session_files.values()):
        pytest.skip("需要本机真实的 Codex 续接会话记录")

    expected_daily = defaultdict(int)
    for endpoints in daily_endpoints.values():
        previous = 0
        for day, total in sorted(endpoints.items()):
            assert total >= previous, "真实记录存在计数重置，需要单独核对统计依据"
            expected_daily[day.isoformat()] += total - previous
            previous = total

    original_home = os.environ.get("CODEX_HOME")
    try:
        os.environ["CODEX_HOME"] = str(tmp_path)
        _TOKEN_FILE_CACHE.clear()
        actual = read_local_token_usage()
        today = datetime.now().date()
        for name, days in (("today", 1), ("week", 7), ("month", 30), ("year", 365)):
            start = (today - timedelta(days=days - 1)).isoformat()
            expected = sum(count for day, count in expected_daily.items() if start <= day <= today.isoformat())
            assert actual["periods"][name] == expected
        year_start = (today - timedelta(days=364)).isoformat()
        assert actual["daily"] == dict(
            sorted((day, count) for day, count in expected_daily.items() if year_start <= day <= today.isoformat())
        )
        assert file_totals > sum(expected_daily.values())
        assert read_local_token_usage() == actual

        duplicate = tmp_path / "archived_sessions" / "duplicate" / "session.jsonl"
        duplicate.parent.mkdir(parents=True)
        copyfile(snapshots[0], duplicate)
        assert read_local_token_usage() == actual
        duplicate.unlink()
        assert read_local_token_usage() == actual

        databases = list(home.glob("state_*.sqlite"))
        if not databases:
            pytest.skip("需要本机真实的 Codex 会话数据库")
        database = max(databases, key=lambda path: int(path.stem.removeprefix("state_")))
        source_connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
        snapshot_connection = sqlite3.connect(tmp_path / database.name)
        try:
            source_connection.backup(snapshot_connection)
            rows = snapshot_connection.execute("SELECT id, tokens_used, created_at, updated_at FROM threads").fetchall()
        finally:
            source_connection.close()
            snapshot_connection.close()

        database_totals = {session_id: count for session_id, count, _, _ in rows}
        combined = read_local_token_usage()
        assert combined["daily"] == actual["daily"]
        expected_totals = {session_id: max(endpoints.values()) for session_id, endpoints in daily_endpoints.items()}
        for session_id, count in database_totals.items():
            expected_totals[session_id] = max(count, expected_totals.get(session_id, 0))
        assert combined["unlogged_tokens"] == sum(expected_totals.values()) - sum(expected_daily.values())
        assert combined["unlogged_tokens"] > 0
        for period, days in (("month", 30), ("year", 365)):
            cutoff = today - timedelta(days=days - 1)
            if all(cutoff <= datetime.fromtimestamp(start).date() <= datetime.fromtimestamp(end).date() <= today
                   for _, _, start, end in rows):
                assert combined["periods"][period] == sum(expected_totals.values())

        # 移走真实日志快照，只保留数据库，核对没有详细日志的统计边界。
        hidden = tmp_path / "saved_sessions"
        (tmp_path / "sessions").rename(hidden)
        database_only = read_local_token_usage()
        assert database_only is not None
        assert database_only["daily"] == {}
        assert database_only["models"] == {}
        for period, days in (("today", 1), ("week", 7), ("month", 30), ("year", 365)):
            cutoff = today - timedelta(days=days - 1)
            selected = [(count, datetime.fromtimestamp(start).date(), datetime.fromtimestamp(end).date())
                        for _, count, start, end in rows if count > 0]
            intersects = [(count, start, end) for count, start, end in selected if end >= cutoff and start <= today]
            if any(start < cutoff or end > today for _, start, end in intersects):
                assert database_only["periods"][period] is None
            else:
                assert database_only["periods"][period] == sum(count for count, _, _ in intersects)
    finally:
        if original_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = original_home
        _TOKEN_FILE_CACHE.clear()

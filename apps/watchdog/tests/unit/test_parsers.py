from datetime import datetime, timezone
from pathlib import Path

import pytest

from apps.watchdog.core.parsers.json_log import parse_json
from apps.watchdog.core.parsers.syslog import parse_syslog
from apps.watchdog.core.parsers.text import parse_text

SD = Path(__file__).parents[2] / "sample_data"


def test_json_parses_sample():
    events, errs = parse_json((SD / "app.log").read_bytes(), "app.log")
    assert errs == []
    assert len(events) == 431
    assert {e.service for e in events} == {"api", "checkout", "worker"}
    assert any(e.level == "error" for e in events)


def test_json_field_aliases_and_epoch():
    data = b'{"ts": 1752919200, "severity": "ERROR", "logger": "svc", "msg": "boom"}\n'
    events, errs = parse_json(data, "x.log")
    assert errs == []
    assert events[0].level == "error" and events[0].service == "svc"
    assert events[0].ts.tzinfo is not None


def test_json_array_form():
    data = b'[{"timestamp":"2026-07-19T10:00:00Z","level":"info","service":"a","message":"m"}]'
    events, _ = parse_json(data, "x")
    assert len(events) == 1 and events[0].service == "a"


def test_json_bad_lines_collected():
    data = b'{"timestamp":"2026-07-19T10:00:00Z","level":"info","service":"a"}\nnot json\n{"level":"info"}\n'
    events, errs = parse_json(data, "x")
    assert len(events) == 1  # one valid, one non-json, one missing-ts
    assert len(errs) == 2


def test_json_all_invalid_raises():
    with pytest.raises(ValueError):
        parse_json(b"not json at all\nstill not\n", "x")


def test_syslog_parses_sample():
    events, errs = parse_syslog((SD / "platform.log").read_bytes(), "platform.log")
    assert len(events) == 221
    assert {e.service for e in events} == {"nginx", "kernel", "sshd"}
    assert any(e.level == "error" for e in events)


def test_syslog_level_detection():
    line = b"Jul 19 10:03:12 host01 nginx[123]: error upstream refused\n"
    events, _ = parse_syslog(line, "x")
    assert events[0].service == "nginx" and events[0].level == "error"
    assert events[0].ts == datetime(2026, 7, 19, 10, 3, 12, tzinfo=timezone.utc)


def test_syslog_non_matching_raises():
    with pytest.raises(ValueError):
        parse_syslog(b"just some random text\nno syslog here\n", "x")


def test_text_parser():
    data = b"2026-07-19T10:00:00 [api] ERROR something broke\n2026-07-19 10:00:01 [api] INFO ok\n"
    events, errs = parse_text(data, "x")
    assert errs == []
    assert events[0].level == "error" and events[0].service == "api"
    assert events[1].level == "info"


def test_text_no_timestamp_raises():
    with pytest.raises(ValueError):
        parse_text(b"no timestamps here\n", "x")

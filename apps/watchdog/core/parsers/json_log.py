"""JSON-lines log parser. Accepts a JSON array or newline-delimited JSON objects."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from apps.watchdog.core.models import LogEvent
from apps.watchdog.core.registry import parser

TS_KEYS = ("timestamp", "ts", "time", "@timestamp", "datetime")
LEVEL_KEYS = ("level", "severity", "lvl", "loglevel")
SERVICE_KEYS = ("service", "logger", "app", "component", "source")
MSG_KEYS = ("message", "msg", "text", "event")


def _first(d: dict, keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def parse_ts(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    s = str(value).strip().replace("Z", "+00:00")
    for fmt in (None,):  # try fromisoformat first
        try:
            dt = datetime.fromisoformat(s)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            break
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%b %d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


@parser("json")
def parse_json(file_bytes: bytes, filename: str = "app.log"):
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8 text: {exc}") from exc

    stripped = text.lstrip()
    if stripped.startswith("["):
        try:
            records = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON array: {exc}") from exc
        lines = [(0, r) for r in records]
    else:
        lines = []
        for i, ln in enumerate(text.splitlines(), start=1):
            ln = ln.strip()
            if not ln:
                continue
            try:
                lines.append((i, json.loads(ln)))
            except json.JSONDecodeError:
                lines.append((i, None))
        if not any(r is not None for _, r in lines):
            raise ValueError("no valid JSON log lines found")

    events, errors = [], []
    for line_no, rec in lines:
        if not isinstance(rec, dict):
            errors.append({"line": line_no, "reason": "not a JSON object"})
            continue
        ts = parse_ts(_first(rec, TS_KEYS))
        if ts is None:
            errors.append({"line": line_no, "reason": "missing/unparsable timestamp"})
            continue
        events.append(LogEvent(
            ts=ts,
            level=str(_first(rec, LEVEL_KEYS) or "info").lower(),
            service=str(_first(rec, SERVICE_KEYS) or "unknown"),
            message=str(_first(rec, MSG_KEYS) or "")))
    return events, errors

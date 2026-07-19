"""Generic text-log parser: ISO timestamp + level keyword anywhere in the line."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from apps.watchdog.core.models import LogEvent
from apps.watchdog.core.registry import parser

TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})")
LEVEL_RE = re.compile(
    r"\b(EMERG|ALERT|CRIT|CRITICAL|ERROR|ERR|WARN|WARNING|NOTICE|INFO|DEBUG|FATAL|PANIC)\b")
SERVICE_RE = re.compile(r"\[([\w\-./]+)\]")


@parser("text")
def parse_text(file_bytes: bytes, filename: str = "app.log"):
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8 text: {exc}") from exc

    events, errors = [], []
    matched = 0
    for line_no, ln in enumerate(text.splitlines(), start=1):
        if not ln.strip():
            continue
        ts_m = TS_RE.search(ln)
        if not ts_m:
            errors.append({"line": line_no, "reason": "no ISO timestamp"})
            continue
        try:
            dt = datetime.fromisoformat(ts_m.group(1).replace(" ", "T"))
            dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            errors.append({"line": line_no, "reason": "unparsable timestamp"})
            continue
        matched += 1
        lvl_m = LEVEL_RE.search(ln)
        svc_m = SERVICE_RE.search(ln)
        events.append(LogEvent(
            ts=dt, level=(lvl_m.group(1).lower() if lvl_m else "info"),
            service=(svc_m.group(1) if svc_m else "unknown"),
            message=ln[ts_m.end():].strip()))
    if matched == 0:
        raise ValueError("no timestamped log lines found")
    return events, errors

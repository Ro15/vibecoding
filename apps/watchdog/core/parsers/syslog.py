"""Syslog-style parser (RFC3164-ish): '<mon day time> host service[pid]: LEVEL msg'."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from apps.watchdog.core.models import LogEvent
from apps.watchdog.core.registry import parser

# Jul 19 10:03:12 host nginx[123]: error something failed
LINE_RE = re.compile(
    r"^(?P<ts>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+\S+\s+"
    r"(?P<service>[\w\-./]+?)(?:\[\d+\])?:\s+(?P<msg>.*)$")

LEVEL_RE = re.compile(
    r"\b(emerg|alert|crit|critical|error|err|warn|warning|notice|info|debug|fatal|panic)\b",
    re.IGNORECASE)

DEFAULT_YEAR = 2026


def _parse_ts(s: str) -> datetime | None:
    for fmt in ("%b %d %H:%M:%S",):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(year=DEFAULT_YEAR, tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


@parser("syslog")
def parse_syslog(file_bytes: bytes, filename: str = "platform.log"):
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8 text: {exc}") from exc

    events, errors = [], []
    matched = 0
    for line_no, ln in enumerate(text.splitlines(), start=1):
        ln = ln.rstrip()
        if not ln:
            continue
        m = LINE_RE.match(ln)
        if not m:
            errors.append({"line": line_no, "reason": "does not match syslog format"})
            continue
        matched += 1
        ts = _parse_ts(m.group("ts"))
        if ts is None:
            errors.append({"line": line_no, "reason": "unparsable timestamp"})
            continue
        msg = m.group("msg")
        lvl_m = LEVEL_RE.search(msg)
        level = (lvl_m.group(1).lower() if lvl_m else "info")
        events.append(LogEvent(ts=ts, level=level,
                               service=m.group("service"), message=msg))
    if matched == 0:
        raise ValueError("no syslog-format lines found")
    return events, errors

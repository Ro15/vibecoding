"""Deterministic sample logs with a seeded error spike.

Run: python apps/watchdog/sample_data/generate.py
Writes app.log (JSON lines) and platform.log (syslog).
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
SEED = 7
BASE = datetime(2026, 7, 19, 10, 0, 0, tzinfo=timezone.utc)

JSON_SERVICES = ["api", "checkout", "worker"]
# minutes (from BASE) during which 'checkout' suffers an error spike
SPIKE_START, SPIKE_END = 12, 14


def generate_json(rng) -> list[dict]:
    events = []
    for minute in range(20):
        for svc in JSON_SERVICES:
            base_rate = {"api": 8, "checkout": 6, "worker": 3}[svc]
            for _ in range(base_rate + rng.randint(0, 3)):
                sec = rng.randint(0, 59)
                ts = BASE + timedelta(minutes=minute, seconds=sec)
                # normal low error rate ~5%
                spiking = svc == "checkout" and SPIKE_START <= minute < SPIKE_END
                if spiking:
                    level = "error" if rng.random() < 0.85 else "info"
                else:
                    level = "error" if rng.random() < 0.05 else \
                        rng.choice(["info", "info", "info", "warn", "debug"])
                events.append({
                    "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                    "level": level, "service": svc,
                    "message": ("request failed: upstream timeout" if level == "error"
                                else "request handled")})
    events.sort(key=lambda e: e["timestamp"])
    return events


def generate_syslog(rng) -> list[str]:
    lines = []
    services = ["nginx", "kernel", "sshd"]
    for minute in range(18):
        for svc in services:
            base_rate = {"nginx": 5, "kernel": 2, "sshd": 2}[svc]
            for _ in range(base_rate + rng.randint(0, 2)):
                sec = rng.randint(0, 59)
                ts = (BASE + timedelta(minutes=minute, seconds=sec)).strftime("%b %d %H:%M:%S")
                spiking = svc == "nginx" and 8 <= minute < 10
                if spiking:
                    lvl = "error" if rng.random() < 0.8 else "info"
                else:
                    lvl = "error" if rng.random() < 0.04 else "info"
                msg = ("error upstream connection refused" if lvl == "error"
                       else "info request served 200")
                lines.append(f"{ts} host01 {svc}[{rng.randint(100,999)}]: {msg}")
    return lines


def main():
    rng = random.Random(SEED)
    events = generate_json(rng)
    with open(HERE / "app.log", "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    rng2 = random.Random(SEED + 1)
    lines = generate_syslog(rng2)
    (HERE / "platform.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(events)} JSON log lines, {len(lines)} syslog lines")


if __name__ == "__main__":
    main()

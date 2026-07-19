"""Policy defaults and typed merge of stored overrides."""
from __future__ import annotations

DEFAULTS: dict[str, object] = {
    "snapshot_retention_days": 90,
    "cpu_idle_threshold_pct": 3.0,
    "vm_rightsize_cpu_pct": 40.0,
    "rightsize_saving_fraction": 0.5,
    "stopped_vm_age_days": 30,
    "severity_high_usd": 50.0,
    "severity_medium_usd": 10.0,
    "owner_tag_keys": "owner,team",
    "untagged_min_cost_usd": 10.0,
    "lb_low_requests": 100.0,
    "natgw_low_gb": 1.0,
    "schedule_enabled": 0,
    "schedule_interval_minutes": 60,
    "webhook_url": "",
}


def merge_policies(overrides: dict[str, str] | None = None) -> dict[str, object]:
    """Overlay stored (string) overrides onto defaults, casting to default's type."""
    merged = dict(DEFAULTS)
    for key, raw in (overrides or {}).items():
        if key not in DEFAULTS:
            continue
        default = DEFAULTS[key]
        try:
            if isinstance(default, float):
                merged[key] = float(raw)
            elif isinstance(default, int):
                merged[key] = int(float(raw))
            else:
                merged[key] = str(raw)
        except (TypeError, ValueError):
            continue  # keep default on bad override
    return merged


def severity_for(monthly_savings: float, policies: dict | None = None) -> str:
    p = policies or DEFAULTS
    if monthly_savings >= p["severity_high_usd"]:
        return "high"
    if monthly_savings >= p["severity_medium_usd"]:
        return "medium"
    return "low"

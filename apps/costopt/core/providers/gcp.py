"""GCP detailed billing export parser (JSON list, BigQuery-export style)."""
from __future__ import annotations

import json
from datetime import date, datetime

from apps.costopt.core.models import NormalizedResource
from apps.costopt.core.registry import provider

_SKU_TYPE_HINTS = (
    ("snapshot", "snapshot"),
    ("pd capacity", "disk"),
    ("persistent disk", "disk"),
    ("static ip", "ip"),
    ("ip charge", "ip"),
    ("load balanc", "lb"),
    ("forwarding rule", "lb"),
    ("cloud nat", "natgw"),
    ("nat gateway", "natgw"),
    ("instance core", "vm"),
    ("instance ram", "vm"),
)


def _resource_type(sku: str, resource_name: str) -> str:
    text = sku.lower()
    for hint, rtype in _SKU_TYPE_HINTS:
        if hint in text:
            return rtype
    name = resource_name.lower()
    for path, rtype in (("/disks/", "disk"), ("/instances/", "vm"),
                        ("/addresses/", "ip"), ("/snapshots/", "snapshot"),
                        ("/forwardingrules/", "lb"), ("/routers/", "natgw")):
        if path in name:
            return rtype
    return "other"


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


@provider("gcp")
def parse_gcp(file_bytes: bytes, billing_period: str | None = None):
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8 text: {exc}") from exc
    try:
        items = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(items, list):
        raise ValueError("GCP export must be a JSON list of billing records")

    errors: list[dict] = []
    agg: dict[str, NormalizedResource] = {}

    for idx, item in enumerate(items, start=1):
        resource = item.get("resource") or {}
        res_id = (resource.get("name") or "").strip()
        if not res_id:
            errors.append({"line": idx, "reason": "missing resource.name"})
            continue
        try:
            cost = float(item.get("cost") or 0.0)
            usage = float((item.get("usage") or {}).get("amount") or 0.0)
        except (TypeError, ValueError):
            errors.append({"line": idx, "reason": "unparsable cost/usage"})
            continue

        labels = {}
        for entry in item.get("labels") or []:
            if isinstance(entry, dict) and entry.get("key"):
                labels[entry["key"]] = entry.get("value")

        sku = ((item.get("sku") or {}).get("description") or "")
        rtype = _resource_type(sku, res_id)

        state = "unknown"
        if rtype == "vm":
            ps = str(labels.get("power_state") or "").lower()
            if ps in ("stopped", "terminated"):
                state = "stopped"
            elif ps == "running":
                state = "running"
        else:
            attach = str(labels.get("attachment_state") or "").lower()
            if attach in ("attached", "unattached", "associated", "unassociated"):
                state = attach

        tags = {}
        if labels.get("owner"):
            tags["owner"] = labels["owner"]
        if labels.get("team"):
            tags["team"] = labels["team"]
        if labels.get("stopped_date"):
            tags["stoppedDate"] = str(labels["stopped_date"])
        for lkey, tkey in (("avg_cpu_pct", "avgCpuPct"),
                           ("request_count", "requestCount"),
                           ("data_processed_gb", "dataProcessedGB")):
            if labels.get(lkey) is not None:
                try:
                    tags[tkey] = float(labels[lkey])
                except (TypeError, ValueError):
                    pass

        period = billing_period or str(item.get("usage_start_time") or "")[:7] or "unknown"
        region = ((item.get("location") or {}).get("region")) or "unknown"

        if res_id in agg:
            agg[res_id].monthly_cost += cost
            agg[res_id].usage_hours += usage
        else:
            agg[res_id] = NormalizedResource(
                provider="gcp", resource_id=res_id, resource_type=rtype,
                region=region, billing_period=period, monthly_cost=cost,
                usage_hours=usage, state=state,
                created_at=_parse_date(labels.get("created_date")), tags=tags)

    for r in agg.values():
        r.monthly_cost = round(r.monthly_cost, 4)
    return list(agg.values()), errors

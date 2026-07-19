"""Azure Cost Management export parser (JSON list or CSV)."""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime

from apps.costopt.core.models import NormalizedResource
from apps.costopt.core.registry import provider

_TYPE_MAP = {
    "microsoft.compute/disks": "disk",
    "microsoft.compute/virtualmachines": "vm",
    "microsoft.network/publicipaddresses": "ip",
    "microsoft.compute/snapshots": "snapshot",
    "microsoft.network/loadbalancers": "lb",
    "microsoft.network/natgateways": "natgw",
}


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _load_items(file_bytes: bytes) -> list[dict]:
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8 text: {exc}") from exc

    stripped = text.lstrip()
    if stripped.startswith("["):
        try:
            items = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc
        if not isinstance(items, list):
            raise ValueError("JSON export must be a list of cost records")
        return items
    # CSV variant
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "ResourceId" not in reader.fieldnames:
        raise ValueError("not an Azure cost export: missing ResourceId column")
    return list(reader)


@provider("azure")
def parse_azure(file_bytes: bytes, billing_period: str | None = None):
    items = _load_items(file_bytes)
    errors: list[dict] = []
    agg: dict[str, NormalizedResource] = {}

    for idx, item in enumerate(items, start=1):
        res_id = (item.get("ResourceId") or "").strip()
        if not res_id:
            errors.append({"line": idx, "reason": "missing ResourceId"})
            continue
        try:
            cost = float(item.get("CostInBillingCurrency") or 0.0)
            qty = float(item.get("Quantity") or 0.0)
        except (TypeError, ValueError):
            errors.append({"line": idx, "reason": "unparsable cost/quantity"})
            continue

        rtype = _TYPE_MAP.get((item.get("ResourceType") or "").lower(), "other")

        info = {}
        raw_info = item.get("AdditionalInfo") or "{}"
        if isinstance(raw_info, dict):
            info = raw_info
        else:
            try:
                info = json.loads(raw_info)
            except (json.JSONDecodeError, TypeError):
                info = {}

        state = "unknown"
        if rtype == "vm":
            ps = str(info.get("powerState") or "").lower()
            if ps in ("stopped", "deallocated"):
                state = "stopped"
            elif ps == "running":
                state = "running"
        else:
            attach = str(info.get("attachmentState") or "").lower()
            if attach:
                state = {"unattached": "unattached", "attached": "attached",
                         "associated": "associated", "unassociated": "unassociated"}.get(attach, "unknown")

        tags = {}
        raw_tags = item.get("Tags") or "{}"
        if isinstance(raw_tags, dict):
            tags.update(raw_tags)
        else:
            try:
                tags.update(json.loads(raw_tags))
            except (json.JSONDecodeError, TypeError):
                pass
        for key in ("avgCpuPct", "requestCount", "dataProcessedGB"):
            if key in info:
                try:
                    tags[key] = float(info[key])
                except (TypeError, ValueError):
                    pass
        if info.get("stoppedDate"):
            tags["stoppedDate"] = str(info["stoppedDate"])

        period = billing_period or str(item.get("Date") or "")[:7] or "unknown"

        if res_id in agg:
            agg[res_id].monthly_cost += cost
            agg[res_id].usage_hours += qty
        else:
            agg[res_id] = NormalizedResource(
                provider="azure",
                resource_id=res_id,
                resource_type=rtype,
                region=item.get("ResourceLocation") or "unknown",
                billing_period=period,
                monthly_cost=cost,
                usage_hours=qty,
                state=state,
                created_at=_parse_date(info.get("createdDate")),
                tags=tags,
            )

    for r in agg.values():
        r.monthly_cost = round(r.monthly_cost, 4)
    return list(agg.values()), errors

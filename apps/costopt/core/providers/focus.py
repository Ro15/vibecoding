"""FOCUS-format parser (FinOps Foundation vendor-neutral billing spec).

Accepts CSV or a JSON list with FOCUS column names. ProviderName sets each
resource's actual cloud so remediation commands stay provider-correct.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime

from apps.costopt.core.models import NormalizedResource
from apps.costopt.core.registry import provider

_TYPE_MAP = {
    "storage volume": "disk",
    "disk": "disk",
    "virtual machine": "vm",
    "compute instance": "vm",
    "public ip address": "ip",
    "ip address": "ip",
    "snapshot": "snapshot",
    "load balancer": "lb",
    "nat gateway": "natgw",
}

_PROVIDER_MAP = {"aws": "aws", "amazon": "aws", "amazon web services": "aws",
                 "azure": "azure", "microsoft": "azure", "microsoft azure": "azure",
                 "gcp": "gcp", "google": "gcp", "google cloud": "gcp"}


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _load_rows(file_bytes: bytes) -> list[dict]:
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8 text: {exc}") from exc
    stripped = text.lstrip()
    if stripped.startswith("["):
        try:
            rows = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc
        if not isinstance(rows, list):
            raise ValueError("FOCUS JSON export must be a list")
        return rows
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "ResourceId" not in reader.fieldnames:
        raise ValueError("not a FOCUS export: missing ResourceId column")
    return list(reader)


@provider("focus")
def parse_focus(file_bytes: bytes, billing_period: str | None = None):
    rows = _load_rows(file_bytes)
    errors: list[dict] = []
    agg: dict[str, NormalizedResource] = {}

    for idx, row in enumerate(rows, start=1):
        res_id = (row.get("ResourceId") or "").strip()
        if not res_id:
            errors.append({"line": idx, "reason": "missing ResourceId"})
            continue
        try:
            cost = float(row.get("BilledCost") or 0.0)
            qty = float(row.get("ConsumedQuantity") or 0.0)
        except (TypeError, ValueError):
            errors.append({"line": idx, "reason": "unparsable BilledCost/ConsumedQuantity"})
            continue

        prov_raw = str(row.get("ProviderName") or "").strip().lower()
        prov = _PROVIDER_MAP.get(prov_raw)
        if prov is None:
            errors.append({"line": idx, "reason": f"unknown ProviderName {prov_raw!r}"})
            continue

        rtype = _TYPE_MAP.get(str(row.get("ResourceType") or "").strip().lower(), "other")

        raw_tags = row.get("Tags") or "{}"
        if isinstance(raw_tags, dict):
            tag_data = raw_tags
        else:
            try:
                tag_data = json.loads(raw_tags)
            except (json.JSONDecodeError, TypeError):
                tag_data = {}

        state = str(tag_data.get("x_state") or "unknown").lower()
        if state not in ("attached", "available", "unattached", "stopped", "running",
                         "associated", "unassociated"):
            state = "unknown"

        tags = {k: v for k, v in tag_data.items()
                if k in ("owner", "team", "stoppedDate")}
        for key in ("avgCpuPct", "requestCount", "dataProcessedGB"):
            if tag_data.get(key) is not None:
                try:
                    tags[key] = float(tag_data[key])
                except (TypeError, ValueError):
                    pass

        period = billing_period or str(row.get("ChargePeriodStart") or "")[:7] or "unknown"

        if res_id in agg:
            agg[res_id].monthly_cost += cost
            agg[res_id].usage_hours += qty
        else:
            agg[res_id] = NormalizedResource(
                provider=prov, resource_id=res_id, resource_type=rtype,
                region=str(row.get("RegionId") or "unknown"), billing_period=period,
                monthly_cost=cost, usage_hours=qty, state=state,
                created_at=_parse_date(tag_data.get("x_createdDate")), tags=tags)

    for r in agg.values():
        r.monthly_cost = round(r.monthly_cost, 4)
    return list(agg.values()), errors

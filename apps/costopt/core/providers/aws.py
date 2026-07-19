"""AWS Cost & Usage Report (CUR) CSV parser."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime

from apps.costopt.core.models import NormalizedResource
from apps.costopt.core.registry import provider

_STATE_MAP = {
    "attached": "attached",
    "available": "available",
    "unattached": "available",
    "stopped": "stopped",
    "running": "running",
    "associated": "associated",
    "unassociated": "unassociated",
}


def _resource_type(usage_type: str, product_code: str, resource_id: str) -> str:
    ut = usage_type.lower()
    if "snapshot" in ut or resource_id.startswith("snap-"):
        return "snapshot"
    if "ebs:volume" in ut or resource_id.startswith("vol-"):
        return "disk"
    if "elasticip" in ut or resource_id.startswith("eipalloc-"):
        return "ip"
    if "loadbalancer" in ut or resource_id.startswith("lb-"):
        return "lb"
    if "natgateway" in ut or resource_id.startswith("nat-"):
        return "natgw"
    if "boxusage" in ut or resource_id.startswith("i-"):
        return "vm"
    return "other"


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


@provider("aws")
def parse_aws(file_bytes: bytes, billing_period: str | None = None):
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8 text: {exc}") from exc

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "lineItem/ResourceId" not in reader.fieldnames:
        raise ValueError("not an AWS CUR export: missing lineItem/ResourceId column")

    errors: list[dict] = []
    agg: dict[str, NormalizedResource] = {}

    for line_no, row in enumerate(reader, start=2):
        res_id = (row.get("lineItem/ResourceId") or "").strip()
        if not res_id:
            errors.append({"line": line_no, "reason": "missing lineItem/ResourceId"})
            continue
        try:
            cost = float(row.get("lineItem/UnblendedCost") or 0.0)
            usage = float(row.get("lineItem/UsageAmount") or 0.0)
        except ValueError:
            errors.append({"line": line_no, "reason": "unparsable cost/usage amount"})
            continue

        usage_type = row.get("lineItem/UsageType") or ""
        period = billing_period or (row.get("lineItem/UsageStartDate") or "")[:7] or "unknown"
        raw_state = (row.get("resourceTags/aws:attachmentState") or "").strip().lower()
        state = _STATE_MAP.get(raw_state, "unknown")

        tags = {}
        if row.get("resourceTags/user:Name"):
            tags["Name"] = row["resourceTags/user:Name"]
        if (row.get("resourceTags/user:owner") or "").strip():
            tags["owner"] = row["resourceTags/user:owner"].strip()
        if (row.get("resourceTags/aws:stoppedDate") or "").strip():
            tags["stoppedDate"] = row["resourceTags/aws:stoppedDate"].strip()
        for col, key in (("resourceTags/aws:cpuAvgPct", "avgCpuPct"),
                         ("resourceTags/aws:requestCount", "requestCount"),
                         ("resourceTags/aws:dataProcessedGB", "dataProcessedGB")):
            raw = (row.get(col) or "").strip()
            if raw:
                try:
                    tags[key] = float(raw)
                except ValueError:
                    pass

        if res_id in agg:
            agg[res_id].monthly_cost += cost
            agg[res_id].usage_hours += usage
        else:
            agg[res_id] = NormalizedResource(
                provider="aws",
                resource_id=res_id,
                resource_type=_resource_type(usage_type, row.get("lineItem/ProductCode") or "", res_id),
                region=row.get("product/region") or "unknown",
                billing_period=period,
                monthly_cost=cost,
                usage_hours=usage,
                state=state,
                created_at=_parse_date(row.get("resourceTags/aws:createdDate") or ""),
                tags=tags,
            )

    for r in agg.values():
        r.monthly_cost = round(r.monthly_cost, 4)
    return list(agg.values()), errors

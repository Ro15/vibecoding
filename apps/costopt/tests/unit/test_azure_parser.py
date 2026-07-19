import json
from datetime import date
from pathlib import Path

from apps.costopt.core.providers.azure import parse_azure

SAMPLE = (Path(__file__).parents[2] / "sample_data" / "azure_costs.json").read_bytes()


def item(**overrides):
    base = {
        "ResourceId": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/disks/d1",
        "ResourceType": "Microsoft.Compute/disks",
        "MeterCategory": "Storage",
        "MeterName": "P10 Disks",
        "CostInBillingCurrency": 10.0,
        "Quantity": 720,
        "ResourceLocation": "eastus",
        "Date": "2026-06-01",
        "Tags": "{}",
        "AdditionalInfo": json.dumps({"attachmentState": "Unattached", "createdDate": "2026-06-01"}),
    }
    base.update(overrides)
    return base


def test_parses_sample_file():
    resources, errors = parse_azure(SAMPLE)
    assert errors == []
    assert len(resources) == 47
    assert all(r.provider == "azure" for r in resources)


def test_type_mapping():
    resources, _ = parse_azure(SAMPLE)
    types = {r.resource_id.rsplit("/", 1)[-1]: r.resource_type for r in resources}
    assert types["orphan-disk-0"] == "disk"
    assert types["idle-vm-0"] == "vm"
    assert types["orphan-ip-0"] == "ip"
    assert types["old-snap-0"] == "snapshot"


def test_state_normalized_lowercase():
    resources, _ = parse_azure(json.dumps([item()]).encode())
    assert resources[0].state == "unattached"


def test_vm_powerstate_maps_to_state():
    it = item(ResourceId="/s/rg/providers/Microsoft.Compute/virtualMachines/v1",
              ResourceType="Microsoft.Compute/virtualMachines",
              AdditionalInfo=json.dumps({"powerState": "stopped", "avgCpuPct": 0.2}))
    resources, _ = parse_azure(json.dumps([it]).encode())
    assert resources[0].resource_type == "vm"
    assert resources[0].state == "stopped"
    assert resources[0].tags.get("avgCpuPct") == 0.2


def test_malformed_additional_info_degrades_to_unknown():
    it = item(AdditionalInfo="{not json")
    resources, errors = parse_azure(json.dumps([it]).encode())
    assert errors == []
    assert resources[0].state == "unknown"


def test_created_date_parsed():
    it = item(AdditionalInfo=json.dumps({"attachmentState": "Attached", "createdDate": "2025-11-02"}))
    resources, _ = parse_azure(json.dumps([it]).encode())
    assert resources[0].created_at == date(2025, 11, 2)


def test_csv_variant_supported():
    rows = [item(), item(ResourceId="/s/rg/providers/Microsoft.Compute/disks/d2")]
    header = ",".join(rows[0].keys())
    def esc(v):
        s = str(v)
        return '"' + s.replace('"', '""') + '"' if ("," in s or '"' in s) else s
    lines = [header] + [",".join(esc(v) for v in r.values()) for r in rows]
    resources, errors = parse_azure("\n".join(lines).encode())
    assert errors == []
    assert len(resources) == 2


def test_missing_resource_id_is_row_error():
    it = item(ResourceId="")
    resources, errors = parse_azure(json.dumps([it, item()]).encode())
    assert len(resources) == 1
    assert len(errors) == 1


def test_structurally_unreadable_raises():
    import pytest
    with pytest.raises(ValueError):
        parse_azure(b"\xff\xfe\x00\x01binary")

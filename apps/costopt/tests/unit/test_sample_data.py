import csv
import io
import json
import random

from apps.costopt.sample_data.generate import generate_aws, generate_azure


def test_aws_sample_has_seeded_waste_and_noise():
    rows = generate_aws(random.Random(42))
    ids = [r["lineItem/ResourceId"] for r in rows]
    assert sum(1 for i in ids if i.startswith("vol-0waste")) == 3
    assert sum(1 for i in ids if i.startswith("i-0stopped")) == 2
    assert sum(1 for i in ids if i.startswith("eipalloc-0waste")) == 3
    assert sum(1 for i in ids if i.startswith("snap-0old")) == 3
    assert len(rows) >= 50  # waste + healthy noise


def test_azure_sample_has_seeded_waste_and_noise():
    items = generate_azure(random.Random(42))
    ids = [i["ResourceId"] for i in items]
    assert sum(1 for i in ids if "orphan-disk" in i) == 3
    assert sum(1 for i in ids if "idle-vm" in i) == 2
    assert sum(1 for i in ids if "orphan-ip" in i) == 2
    assert sum(1 for i in ids if "old-snap" in i) == 3
    assert len(items) >= 40


def test_generation_is_deterministic():
    a = generate_aws(random.Random(42))
    b = generate_aws(random.Random(42))
    assert a == b


def test_aws_rows_serialize_to_csv():
    rows = generate_aws(random.Random(42))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    assert "lineItem/ResourceId" in buf.getvalue()


def test_azure_items_serialize_to_json():
    items = generate_azure(random.Random(42))
    payload = json.dumps(items)
    assert "Microsoft.Compute/disks" in payload

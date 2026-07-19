from pathlib import Path

from apps.guardrail.core.engine import run_policies
from apps.guardrail.core.models import IacResource
from apps.guardrail.core.parsers.hcl import parse_hcl
from apps.guardrail.core.scoring import grade, risk_score

SD = Path(__file__).parents[2] / "sample_data"


def r(rtype, **config):
    return IacResource(address="a.b", provider="aws", rtype=rtype, raw_type="aws_x",
                       name="b", config=config)


def test_engine_runs_all_and_sorts_by_severity():
    res, _ = parse_hcl((SD / "insecure.tf").read_bytes(), "insecure.tf")
    findings = run_policies(res)
    severities = [f.severity for f in findings]
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    assert severities == sorted(severities, key=lambda s: order[s])
    assert findings[0].severity == "critical"


def test_engine_skips_unknown_types():
    other = IacResource(address="x", provider="aws", rtype="other", raw_type="aws_thing",
                        name="x", config={})
    assert run_policies([other]) == []


def test_engine_empty():
    assert run_policies([]) == []


def test_risk_score_and_grade():
    assert risk_score([]) == 0 and grade(0) == "A+"
    crit = r("security_group", ingress=[{"from_port": 0, "to_port": 65535, "cidr": "0.0.0.0/0"}])
    findings = run_policies([crit])
    assert risk_score(findings) == 80  # critical(40)+high ssh(20)+high rdp(20)
    assert grade(80) == "F"


def test_score_bands():
    assert grade(10) == "A"
    assert grade(20) == "B"
    assert grade(40) == "C"
    assert grade(60) == "D"
    assert grade(80) == "F"


def test_secure_scores_clean():
    res, _ = parse_hcl((SD / "secure.tf").read_bytes(), "secure.tf")
    assert run_policies(res) == []
    assert risk_score(run_policies(res)) == 0

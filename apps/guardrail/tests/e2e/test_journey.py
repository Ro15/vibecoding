"""Playwright (Chromium) browser journey for Guardrail."""
from pathlib import Path

SD = Path(__file__).parents[2] / "sample_data"


def _scan(dash, fmt, name):
    dash.evaluate("document.querySelector('#toast').className = ''")
    dash.select_option("#format-select", fmt)
    dash.set_input_files("#file-input", str(SD / name))
    dash.click("#upload-form button[type=submit]")
    dash.wait_for_selector("#toast.show")
    return dash.inner_text("#toast")


def test_smoke_loads_empty(dash):
    assert "Guardrail" in dash.title()
    dash.wait_for_selector("#grade")
    assert dash.inner_text("#grade") == "A+"
    assert "No scan yet" in dash.inner_text("#scan-source")


def test_scan_insecure_tf(dash):
    msg = _scan(dash, "hcl", "insecure.tf")
    assert "risk 100" in msg and "grade F" in msg
    dash.wait_for_selector("#findings-table tr.f-row")
    assert dash.inner_text("#grade") == "F"
    assert int(dash.inner_text("#tile-findings")) == 12
    assert int(dash.inner_text("#tile-resources")) == 7
    # charts + gauge rendered
    for cid in ("gauge", "chart-severity", "chart-rtype", "chart-trend"):
        box = dash.locator(f"#{cid}").bounding_box()
        assert box and box["width"] > 40 and box["height"] > 40
    # critical finding sorted first
    first = dash.locator("#findings-table tr.f-row").first
    assert "critical" in first.inner_text().lower()


def test_expand_finding_shows_remediation(dash):
    dash.wait_for_selector("#findings-table tr.f-row")
    dash.locator("#findings-table tr.f-row").first.click()
    dash.wait_for_selector(".remediation")
    assert dash.inner_text(".remediation").strip() != ""


def test_filter_by_severity(dash):
    dash.wait_for_selector("#findings-table tr.f-row")
    dash.select_option("#filter-severity", "high")
    dash.wait_for_function(
        "() => [...document.querySelectorAll('#findings-table tr.f-row .badge')]"
        ".every(b => b.textContent.trim() === 'high')")
    dash.select_option("#filter-severity", "")


def test_scan_cloudformation(dash):
    msg = _scan(dash, "cloudformation", "insecure_cfn.yaml")
    assert "grade F" in msg
    dash.wait_for_selector("#findings-table tr.f-row")
    assert "insecure_cfn.yaml" in dash.inner_text("#scan-source")


def test_secure_file_is_clean(dash):
    _scan(dash, "hcl", "secure.tf")
    dash.wait_for_function("() => document.querySelector('#grade').textContent === 'A+'")
    assert int(dash.inner_text("#tile-findings")) == 0


def test_theme_toggle_persists(dash):
    initial = dash.get_attribute("html", "data-theme")
    dash.click("#btn-theme")
    flipped = dash.get_attribute("html", "data-theme")
    assert flipped != initial
    dash.reload()
    dash.wait_for_selector("#grade")
    assert dash.get_attribute("html", "data-theme") == flipped
    dash.click("#btn-theme")

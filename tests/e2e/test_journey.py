"""Playwright (Chromium) browser E2E: full user journey on the live app.

Tests run in file order against one server session; the journey builds state
(upload -> analyze) that later tests reuse.
"""
import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
AWS_SAMPLE = ROOT / "sample_data" / "aws_cur.csv"
AZURE_SAMPLE = ROOT / "sample_data" / "azure_costs.json"


def test_smoke_dashboard_loads_empty(dash):
    assert "CostOpt" in dash.title()
    dash.wait_for_selector("#tile-waste")
    assert dash.inner_text("#tile-waste").startswith("$0.00")
    assert "No findings" in dash.inner_text("#findings-table tbody")


def test_upload_aws_export_via_ui(dash):
    dash.set_input_files("#file-input", str(AWS_SAMPLE))
    assert "aws_cur.csv" in dash.inner_text("#file-name")
    dash.click("#upload-form button[type=submit]")
    dash.wait_for_selector("#toast.show")
    assert "Ingested 53 resources" in dash.inner_text("#toast")


def test_upload_azure_export_via_ui(dash):
    dash.select_option("#provider-select", "azure")
    dash.set_input_files("#file-input", str(AZURE_SAMPLE))
    dash.click("#upload-form button[type=submit]")
    dash.wait_for_selector("#toast.show")
    assert "Ingested 41 resources" in dash.inner_text("#toast")


def test_run_analysis_populates_dashboard(dash):
    dash.click("#btn-analyze")
    dash.wait_for_selector("#findings-table tr.f-row")
    # tiles populated
    waste = dash.inner_text("#tile-waste")
    assert re.match(r"\$\d", waste) and waste != "$0.00/mo"
    assert int(dash.inner_text("#tile-open")) == 21
    assert int(dash.inner_text("#tile-resources")) == 94
    # charts drawn (canvases have nonzero size)
    for cid in ("chart-category", "chart-provider", "chart-trend"):
        box = dash.locator(f"#{cid}").bounding_box()
        assert box and box["width"] > 50 and box["height"] > 50
    # top offenders list filled
    assert dash.locator("#top-offenders li").count() == 5


def test_expand_finding_shows_remediation_commands(dash):
    dash.wait_for_selector("#findings-table tr.f-row")
    first = dash.locator("#findings-table tr.f-row").first
    resource = first.locator("td.mono").get_attribute("title")
    first.click()
    dash.wait_for_selector(".rem-steps")
    cli_text = dash.inner_text(".rem-steps")
    # command references the actual resource (azure ids show name segment)
    tail = resource.rstrip("/").rsplit("/", 1)[-1]
    assert tail in cli_text
    assert "destructive" in cli_text
    assert dash.locator(".btn-copy").count() >= 2


def test_copy_button_gives_feedback(dash):
    dash.wait_for_selector("#findings-table tr.f-row")
    if dash.locator(".rem-steps").count() == 0:
        dash.locator("#findings-table tr.f-row").first.click()
        dash.wait_for_selector(".rem-steps")
    dash.locator(".btn-copy").first.click()
    dash.wait_for_selector(".btn-copy:has-text('Copied!')")


def test_dismiss_finding_updates_status(dash):
    dash.wait_for_selector("#findings-table tr.f-row")
    open_before = int(dash.inner_text("#tile-open"))
    dash.locator(".act-dismiss").first.click()
    dash.wait_for_selector("#toast.show")
    dash.wait_for_function(
        f"() => document.querySelector('#tile-open').textContent == '{open_before - 1}'")
    # filter to dismissed shows the row
    dash.select_option("#filter-status", "dismissed")
    dash.wait_for_selector(".badge.st-dismissed")
    dash.select_option("#filter-status", "")


def test_filters_narrow_findings(dash):
    dash.wait_for_selector("#findings-table tr.f-row")
    dash.select_option("#filter-rule", "orphaned_ip")
    dash.wait_for_function(
        "() => [...document.querySelectorAll('#findings-table tr.f-row td:nth-child(3)')]"
        ".every(td => td.textContent.includes('Orphaned IP'))")
    dash.select_option("#filter-rule", "")


def test_remediation_script_download(dash, server):
    with dash.expect_download() as dl:
        dash.click("#btn-script-aws")
    path = dl.value.path()
    content = Path(path).read_text(encoding="utf-8")
    assert content.startswith("#!/usr/bin/env bash")
    assert "delete-volume" in content


def test_theme_toggle_persists_across_reload(dash):
    initial = dash.get_attribute("html", "data-theme")
    dash.click("#btn-theme")
    flipped = dash.get_attribute("html", "data-theme")
    assert flipped != initial
    dash.reload()
    dash.wait_for_selector("#tile-waste")
    assert dash.get_attribute("html", "data-theme") == flipped
    dash.click("#btn-theme")  # restore

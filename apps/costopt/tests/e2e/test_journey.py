"""Playwright (Chromium) browser E2E: full user journey on the live app.

Tests run in file order against one server session; the journey builds state
(upload -> analyze) that later tests reuse.
"""
import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
AWS_SAMPLE = ROOT / "sample_data" / "aws_cur.csv"
AWS_PREV = ROOT / "sample_data" / "aws_cur_prev.csv"
AZURE_SAMPLE = ROOT / "sample_data" / "azure_costs.json"
GCP_SAMPLE = ROOT / "sample_data" / "gcp_billing.json"


def _upload(dash, provider, path):
    dash.evaluate("document.querySelector('#toast').className = ''")  # clear stale toast
    dash.select_option("#provider-select", provider)
    dash.set_input_files("#file-input", str(path))
    dash.click("#upload-form button[type=submit]")
    dash.wait_for_selector("#toast.show")
    return dash.inner_text("#toast")


def test_smoke_dashboard_loads_empty(dash):
    assert "CostOpt" in dash.title()
    dash.wait_for_selector("#tile-waste")
    assert dash.inner_text("#tile-waste").startswith("$0.00")
    assert dash.inner_text("#tile-realized").startswith("$0.00")
    assert "No findings" in dash.inner_text("#findings-table tbody")


def test_upload_all_providers_via_ui(dash):
    assert "Ingested 64 resources" in _upload(dash, "aws", AWS_SAMPLE)
    assert "Ingested 47 resources" in _upload(dash, "azure", AZURE_SAMPLE)
    assert "Ingested 12 resources" in _upload(dash, "gcp", GCP_SAMPLE)
    assert "Ingested 13 resources" in _upload(dash, "aws", AWS_PREV)


def test_run_analysis_populates_dashboard(dash):
    dash.click("#btn-analyze")
    dash.wait_for_selector("#findings-table tr.f-row")
    waste = dash.inner_text("#tile-waste")
    assert re.match(r"\$\d", waste) and waste != "$0.00/mo"
    assert int(dash.inner_text("#tile-open")) == 40
    assert int(dash.inner_text("#tile-resources")) == 136  # 123 June + 13 May
    for cid in ("chart-category", "chart-provider", "chart-months", "chart-trend"):
        box = dash.locator(f"#{cid}").bounding_box()
        assert box and box["width"] > 50 and box["height"] > 50
    assert dash.locator("#top-offenders li").count() == 5
    # ownership card shows accountable teams incl. the untagged bucket
    owners = dash.inner_text("#by-owner")
    assert "team-platform" in owners and "(untagged)" in owners


def test_expand_finding_shows_remediation_commands(dash):
    dash.wait_for_selector("#findings-table tr.f-row")
    first = dash.locator("#findings-table tr.f-row").first
    resource = first.locator("td.mono").get_attribute("title")
    first.click()
    dash.wait_for_selector(".rem-steps")
    cli_text = dash.inner_text(".rem-steps")
    tail = resource.rstrip("/").rsplit("/", 1)[-1]
    assert tail in cli_text
    assert "destructive" in cli_text
    assert dash.locator(".btn-copy").count() >= 2


def test_dry_run_execution_shows_output(dash):
    dash.wait_for_selector("#findings-table tr.f-row")
    if dash.locator(".rem-steps").count() == 0:
        dash.locator("#findings-table tr.f-row").first.click()
        dash.wait_for_selector(".rem-steps")
    dash.locator(".act-dryrun").click()
    dash.wait_for_selector(".exec-output:not([hidden])")
    output = dash.inner_text(".exec-output")
    assert "[dry-run]" in output and "DESTRUCTIVE" in output
    # status unchanged by a dry run
    assert int(dash.inner_text("#tile-open")) == 40


def test_approved_execution_marks_remediated_and_updates_realized(dash):
    dash.wait_for_selector("#findings-table tr.f-row")
    open_before = int(dash.inner_text("#tile-open"))
    if dash.locator(".rem-steps").count() == 0:
        dash.locator("#findings-table tr.f-row").first.click()
        dash.wait_for_selector(".rem-steps")
    dash.once("dialog", lambda d: d.accept())
    dash.locator(".act-execute").click()
    dash.wait_for_function(
        f"() => document.querySelector('#tile-open').textContent == '{open_before - 1}'")
    realized = dash.inner_text("#tile-realized")
    assert realized != "$0.00/mo"


def test_copy_button_gives_feedback(dash):
    dash.wait_for_selector("#findings-table tr.f-row")
    dash.locator("#findings-table tr.f-row").first.click()
    dash.wait_for_selector(".rem-steps")
    dash.locator(".btn-copy").first.click()
    dash.wait_for_selector(".btn-copy:has-text('Copied!')")


def test_dismiss_finding_updates_status(dash):
    dash.wait_for_selector("#findings-table tr.f-row")
    dash.select_option("#filter-status", "open")  # only open rows are dismissible
    dash.wait_for_selector(".badge.st-open")
    open_before = int(dash.inner_text("#tile-open"))
    dash.locator(".act-dismiss").first.click()
    dash.wait_for_selector("#toast.show")
    dash.wait_for_function(
        f"() => document.querySelector('#tile-open').textContent == '{open_before - 1}'")
    dash.select_option("#filter-status", "dismissed")
    dash.wait_for_selector(".badge.st-dismissed")
    dash.select_option("#filter-status", "")


def test_filters_narrow_findings(dash):
    dash.wait_for_selector("#findings-table tr.f-row")
    dash.select_option("#filter-rule", "oversized_vm")
    dash.wait_for_function(
        "() => [...document.querySelectorAll('#findings-table tr.f-row td:nth-child(3)')]"
        ".every(td => td.textContent.includes('Oversized VM'))")
    dash.select_option("#filter-rule", "")
    dash.select_option("#filter-provider", "gcp")
    dash.wait_for_function(
        "() => [...document.querySelectorAll('#findings-table tr.f-row td:nth-child(5)')]"
        ".every(td => td.textContent === 'GCP')")
    dash.select_option("#filter-provider", "")


def test_settings_modal_saves_policies(dash):
    dash.click("#btn-settings")
    dash.wait_for_selector("#settings-modal:not([hidden])")
    assert dash.input_value("#pol-retention") == "90"
    dash.fill("#pol-retention", "120")
    dash.click("#btn-settings-save")
    dash.wait_for_selector("#settings-modal[hidden]", state="attached")
    dash.wait_for_selector("#toast.show")
    # persisted server-side
    dash.click("#btn-settings")
    dash.wait_for_selector("#settings-modal:not([hidden])")
    assert dash.input_value("#pol-retention") == "120"
    dash.fill("#pol-retention", "90")  # restore
    dash.click("#btn-settings-save")
    dash.wait_for_selector("#settings-modal[hidden]", state="attached")


def test_remediation_script_download(dash, server):
    with dash.expect_download() as dl:
        dash.click("#btn-script-aws")
    content = Path(dl.value.path()).read_text(encoding="utf-8")
    assert content.startswith("#!/usr/bin/env bash")
    assert "delete-volume" in content
    with dash.expect_download() as dl2:
        dash.click("#btn-script-gcp")
    assert "gcloud" in Path(dl2.value.path()).read_text(encoding="utf-8")


def test_theme_toggle_persists_across_reload(dash):
    initial = dash.get_attribute("html", "data-theme")
    dash.click("#btn-theme")
    flipped = dash.get_attribute("html", "data-theme")
    assert flipped != initial
    dash.reload()
    dash.wait_for_selector("#tile-waste")
    assert dash.get_attribute("html", "data-theme") == flipped
    dash.click("#btn-theme")  # restore

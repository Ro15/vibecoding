"""Playwright (Chromium) browser journey for Watchdog."""
from pathlib import Path

SD = Path(__file__).parents[2] / "sample_data"


def _analyze(dash, fmt, name):
    dash.evaluate("document.querySelector('#toast').className = ''")
    dash.select_option("#format-select", fmt)
    dash.set_input_files("#file-input", str(SD / name))
    dash.click("#upload-form button[type=submit]")
    dash.wait_for_selector("#toast.show")
    return dash.inner_text("#toast")


def test_smoke_loads_empty(dash):
    assert "Watchdog" in dash.title()
    dash.wait_for_selector("#tile-events")
    assert dash.inner_text("#tile-events") == "0"
    assert "No alerts" in dash.inner_text("#alert-feed")


def test_analyze_json_detects_spike(dash):
    msg = _analyze(dash, "json", "app.log")
    assert "anomalies" in msg and "alerts" in msg
    dash.wait_for_selector("#alert-feed .alert")
    assert dash.inner_text("#tile-events") == "431"
    assert int(dash.inner_text("#tile-anoms")) >= 2
    assert dash.inner_text("#tile-worst") == "checkout"
    # health + methods charts drawn
    for cid in ("chart-health", "chart-methods"):
        box = dash.locator(f"#{cid}").bounding_box()
        assert box and box["width"] > 50 and box["height"] > 40
    # service health tiles + alert feed populated
    assert dash.locator("#service-tiles .svc-tile").count() == 3
    assert dash.locator("#alert-feed .alert").count() >= 1


def test_alert_feed_shows_simulated_webhook(dash):
    dash.wait_for_selector("#alert-feed .alert")
    txt = dash.inner_text("#alert-feed")
    assert "simulated" in txt
    assert "error spike" in txt.lower()


def test_replay_animates_and_completes(dash):
    dash.wait_for_selector("#alert-feed .alert")
    dash.click("#btn-replay")
    # LIVE badge appears during replay
    dash.wait_for_selector("#replay-badge:not([hidden])")
    # and the completion toast fires
    dash.wait_for_function(
        "() => document.querySelector('#toast').textContent.includes('Replay complete')",
        timeout=15000)
    dash.wait_for_selector("#replay-badge[hidden]", state="attached")


def test_analyze_syslog(dash):
    msg = _analyze(dash, "syslog", "platform.log")
    dash.wait_for_selector("#alert-feed .alert")
    svcs = dash.locator("#service-tiles .svc-tile")
    assert svcs.count() == 3  # nginx, kernel, sshd


def test_theme_toggle_persists(dash):
    initial = dash.get_attribute("html", "data-theme")
    dash.click("#btn-theme")
    flipped = dash.get_attribute("html", "data-theme")
    assert flipped != initial
    dash.reload()
    dash.wait_for_selector("#tile-events")
    assert dash.get_attribute("html", "data-theme") == flipped
    dash.click("#btn-theme")

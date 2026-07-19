"""Playwright E2E fixtures for Watchdog: live uvicorn + fresh temp DB."""
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[4]  # repo root
PORT = 8767
BASE_URL = f"http://127.0.0.1:{PORT}"


def _wait_for_port(port, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.25)
    raise RuntimeError(f"server did not start on port {port}")


@pytest.fixture(scope="session")
def server():
    db_path = os.path.join(tempfile.mkdtemp(prefix="watchdog_e2e_"), "e2e.db")
    env = {**os.environ, "WATCHDOG_DB": db_path}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "apps.watchdog.api.main:app",
         "--port", str(PORT), "--log-level", "warning"],
        cwd=str(ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_for_port(PORT)
        yield BASE_URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture()
def dash(server, page):
    page.goto(server)
    return page

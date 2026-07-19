/* Watchdog dashboard */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const root = document.documentElement;
  let charts = {};
  let healthData = null;
  let replayTimer = null;

  const savedTheme = localStorage.getItem("watchdog-theme");
  if (savedTheme) root.dataset.theme = savedTheme;
  $("#btn-theme").addEventListener("click", () => {
    root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("watchdog-theme", root.dataset.theme);
    refresh();
  });

  const cssVar = (n) => getComputedStyle(root).getPropertyValue(n).trim();
  const SERIES = () => [cssVar("--series-1"), cssVar("--series-2"), cssVar("--series-3"),
                        cssVar("--series-4"), cssVar("--sev-high")];
  let toastTimer;
  function toast(msg, err = false) {
    const el = $("#toast");
    el.textContent = msg;
    el.className = "show" + (err ? " error" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (el.className = ""), 4000);
  }
  async function api(path, opts = {}) {
    const res = await fetch(path, opts);
    if (!res.ok) {
      let d = res.statusText;
      try { const b = await res.json(); d = b.detail || b.error?.message || d;
            if (typeof d === "object") d = JSON.stringify(d); } catch {}
      throw new Error(d);
    }
    return res;
  }
  const fmtTime = (iso) => iso.slice(11, 16);

  function buildHealthChart(upTo) {
    const grid = cssVar("--grid");
    const cols = SERIES();
    const svcs = healthData.services;
    const labels = (healthData.overall || []).map((o) => fmtTime(o.t));
    const n = upTo == null ? labels.length : upTo;
    const datasets = svcs.map((s, i) => {
      const col = cols[i % cols.length];
      const anomT = new Set(s.anomalies.map((a) => a.t));
      return {
        label: s.service,
        data: s.points.slice(0, n).map((p) => p.errors),
        borderColor: col, backgroundColor: col, borderWidth: 2, tension: 0.25,
        pointRadius: s.points.slice(0, n).map((p) => anomT.has(p.t) ? 6 : 0),
        pointBackgroundColor: s.points.slice(0, n).map((p) =>
          anomT.has(p.t) ? cssVar("--sev-high") : col),
        pointBorderColor: cssVar("--surface-1", "#000"),
      };
    });
    if (charts.health) charts.health.destroy();
    Chart.defaults.color = cssVar("--ink-2");
    charts.health = new Chart($("#chart-health"), {
      type: "line",
      data: { labels: labels.slice(0, n), datasets },
      options: { maintainAspectRatio: false, animation: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false },
          tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${c.parsed.y} errors` } } },
        scales: { x: { grid: { display: false }, border: { color: grid },
                       ticks: { maxTicksLimit: 10 } },
                  y: { beginAtZero: true, grid: { color: grid }, border: { display: false },
                       title: { display: true, text: "errors / min" } } } },
    });
    // legend
    $("#svc-legend").innerHTML = svcs.map((s, i) =>
      `<span><span class="dot" style="background:${cols[i % cols.length]}"></span>${s.service}</span>`).join("");
  }

  function renderMethods(summary) {
    const grid = cssVar("--grid");
    const methods = Object.keys(summary.by_method);
    if (charts.methods) charts.methods.destroy();
    charts.methods = new Chart($("#chart-methods"), {
      type: "bar",
      data: { labels: methods.map((m) => m === "ewma_zscore" ? "EWMA z-score" : "IsolationForest"),
        datasets: [{ data: methods.map((m) => summary.by_method[m]),
          backgroundColor: [cssVar("--series-1"), cssVar("--series-3")], borderRadius: 4,
          maxBarThickness: 60 }] },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false }, border: { color: grid } },
                  y: { beginAtZero: true, grid: { color: grid }, border: { display: false },
                       ticks: { precision: 0 } } } },
    });
  }

  async function loadHealth() {
    healthData = await (await api("/api/health")).json();
    buildHealthChart(null);
  }

  async function loadSummary() {
    const s = await (await api("/api/summary")).json();
    $("#tile-events").textContent = s.event_count;
    $("#tile-errrate").textContent = (s.error_rate * 100).toFixed(1) + "%";
    $("#tile-anoms").textContent = s.anomaly_count;
    $("#tile-alerts").textContent = s.alert_count;
    $("#tile-worst").textContent = s.worst_service || "—";
    renderMethods(s);
    // service tiles
    const el = $("#service-tiles");
    const svcs = Object.entries(s.by_service);
    if (!svcs.length) { el.innerHTML = '<p class="empty">No data yet.</p>'; return; }
    el.innerHTML = svcs.sort((a, b) => b[1] - a[1]).map(([svc, errs]) => {
      const cls = errs > 20 ? "critical" : errs > 5 ? "warn" : "good";
      return `<div class="svc-tile"><span class="name"><span class="status-dot status-${cls}"></span>${svc}</span>
              <span class="meta">${errs} errors</span></div>`;
    }).join("");
  }

  async function loadAlerts() {
    const alerts = await (await api("/api/alerts")).json();
    const el = $("#alert-feed");
    if (!alerts.length) {
      el.innerHTML = '<p class="empty">No alerts — a clean signal means healthy services. 🎉</p>';
      return;
    }
    el.innerHTML = alerts.map((a) => `
      <div class="alert ${a.severity}">
        <div class="a-head"><span class="a-svc">${a.service} · ${a.severity}</span>
          <span class="a-method">${a.method} · ${fmtTime(a.bucket_start)} · ${a.delivered ? "delivered" : "simulated"}</span></div>
        <div class="a-summary">${a.summary}</div>
      </div>`).join("");
  }

  // live replay: animate the health chart drawing bucket-by-bucket
  function startReplay() {
    if (!healthData || !healthData.overall.length) return toast("Analyze a log first.", true);
    if (replayTimer) { clearInterval(replayTimer); replayTimer = null; }
    const total = healthData.overall.length;
    let i = 1;
    $("#replay-badge").hidden = false;
    replayTimer = setInterval(() => {
      buildHealthChart(i);
      i++;
      if (i > total) {
        clearInterval(replayTimer); replayTimer = null;
        $("#replay-badge").hidden = true;
        buildHealthChart(null);
        toast("Replay complete — spikes marked in red.");
      }
    }, Math.max(120, Math.floor(8000 / total)));
  }
  $("#btn-replay").addEventListener("click", startReplay);

  $("#file-input").addEventListener("change", (e) =>
    ($("#file-name").textContent = e.target.files[0]?.name || "Choose log file…"));

  $("#upload-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = $("#file-input").files[0];
    if (!file) return toast("Pick a log file first.", true);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("format", $("#format-select").value);
    try {
      const b = await (await api("/api/ingest", { method: "POST", body: fd })).json();
      toast(`Analyzed ${b.event_count} events: ${b.anomaly_count} anomalies, ${b.alert_count} alerts.`);
      await refresh();
    } catch (err) { toast("Analysis failed: " + err.message, true); }
  });

  async function refresh() {
    await Promise.all([loadHealth(), loadSummary(), loadAlerts()]);
  }
  refresh().catch((err) => toast("Failed to load: " + err.message, true));
})();

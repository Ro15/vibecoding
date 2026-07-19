/* Guardrail dashboard */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const root = document.documentElement;
  let charts = {};

  const savedTheme = localStorage.getItem("guardrail-theme");
  if (savedTheme) root.dataset.theme = savedTheme;
  $("#btn-theme").addEventListener("click", () => {
    root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("guardrail-theme", root.dataset.theme);
    refresh();
  });

  const cssVar = (n) => getComputedStyle(root).getPropertyValue(n).trim();
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
      let detail = res.statusText;
      try { const b = await res.json(); detail = b.detail || b.error?.message || detail;
            if (typeof detail === "object") detail = JSON.stringify(detail); } catch {}
      throw new Error(detail);
    }
    return res;
  }

  const SEV_ORDER = ["critical", "high", "medium", "low"];
  const sevColor = () => ({
    critical: cssVar("--sev-high"), high: cssVar("--sev-med"),
    medium: cssVar("--series-1"), low: cssVar("--ink-muted"),
  });

  function drawGauge(score, grade) {
    const cv = $("#gauge");
    const ctx = cv.getContext("2d");
    ctx.clearRect(0, 0, cv.width, cv.height);
    const cx = cv.width / 2, cy = cv.height - 10, rad = 95, lw = 18;
    // track
    ctx.beginPath();
    ctx.lineWidth = lw; ctx.lineCap = "round";
    ctx.strokeStyle = cssVar("--grid");
    ctx.arc(cx, cy, rad, Math.PI, 2 * Math.PI);
    ctx.stroke();
    // value arc — color by risk
    const frac = Math.max(0, Math.min(1, score / 100));
    const col = score >= 75 ? cssVar("--sev-high") : score >= 50 ? cssVar("--sev-med")
              : score >= 30 ? cssVar("--series-1") : cssVar("--good");
    ctx.beginPath();
    ctx.strokeStyle = col;
    ctx.arc(cx, cy, rad, Math.PI, Math.PI + Math.PI * frac);
    ctx.stroke();
    const g = $("#grade");
    g.textContent = grade;
    g.className = "grade g-" + (grade[0] || "A");
    $("#score-num").textContent = score + " / 100 risk";
  }

  function renderCharts(summary) {
    const ink2 = cssVar("--ink-2"), grid = cssVar("--grid");
    Object.values(charts).forEach((c) => c.destroy());
    charts = {};
    Chart.defaults.color = ink2;
    Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';

    const sc = sevColor();
    const sevLabels = SEV_ORDER.filter((s) => s in summary.by_severity);
    charts.severity = new Chart($("#chart-severity"), {
      type: "doughnut",
      data: { labels: sevLabels,
        datasets: [{ data: sevLabels.map((s) => summary.by_severity[s]),
          backgroundColor: sevLabels.map((s) => sc[s]), borderWidth: 2,
          borderColor: cssVar("--glass-border") }] },
      options: { maintainAspectRatio: false, cutout: "60%",
        plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } } } },
    });

    const rtypes = Object.keys(summary.by_rtype);
    charts.rtype = new Chart($("#chart-rtype"), {
      type: "bar",
      data: { labels: rtypes,
        datasets: [{ data: rtypes.map((t) => summary.by_rtype[t]),
          backgroundColor: cssVar("--series-1"), borderRadius: 4, maxBarThickness: 40 }] },
      options: { maintainAspectRatio: false, indexAxis: "y",
        plugins: { legend: { display: false } },
        scales: { x: { grid: { color: grid }, border: { display: false }, ticks: { precision: 0 } },
                  y: { grid: { display: false }, border: { color: grid } } } },
    });

    const trend = summary.scan_trend;
    charts.trend = new Chart($("#chart-trend"), {
      type: "line",
      data: { labels: trend.map((t) => "#" + t.scan_id),
        datasets: [{ data: trend.map((t) => t.risk_score), borderColor: cssVar("--sev-high"),
          borderWidth: 2, pointRadius: 4, pointBackgroundColor: cssVar("--sev-high"),
          tension: 0.25 }] },
      options: { maintainAspectRatio: false,
        plugins: { legend: { display: false },
          tooltip: { callbacks: { label: (c) => ` risk ${c.parsed.y} (${trend[c.dataIndex].grade})` } } },
        scales: { x: { grid: { display: false }, border: { color: grid } },
                  y: { min: 0, max: 100, grid: { color: grid }, border: { display: false } } } },
    });
  }

  async function loadSummary() {
    const s = await (await api("/api/summary")).json();
    drawGauge(s.risk_score, s.grade);
    $("#scan-source").textContent = s.source
      ? `${s.source} · ${s.finding_count} findings` : "No scan yet";
    $("#tile-resources").textContent = s.resource_count;
    $("#tile-findings").textContent = s.finding_count;
    $("#tile-highrisk").textContent = (s.by_severity.critical || 0) + (s.by_severity.high || 0);
    $("#tile-frameworks").textContent = Object.keys(s.by_framework).length;
    // populate rtype filter
    const sel = $("#filter-rtype");
    const cur = sel.value;
    sel.innerHTML = '<option value="">All resource types</option>' +
      Object.keys(s.by_rtype).map((t) => `<option value="${t}">${t}</option>`).join("");
    sel.value = cur;
    renderCharts(s);
  }

  async function loadFindings() {
    const p = new URLSearchParams();
    if ($("#filter-severity").value) p.set("severity", $("#filter-severity").value);
    if ($("#filter-rtype").value) p.set("rtype", $("#filter-rtype").value);
    const rows = await (await api("/api/findings?" + p)).json();
    const tb = $("#findings-table tbody");
    tb.innerHTML = "";
    if (!rows.length) {
      tb.innerHTML = '<tr class="empty-row"><td colspan="7">No findings match — a clean scan means an A+ grade. 🎉</td></tr>';
      return;
    }
    for (const f of rows) {
      const tr = document.createElement("tr");
      tr.className = "f-row";
      tr.dataset.id = f.id;
      tr.innerHTML = `<td class="expander">▸</td>
        <td><span class="badge ${f.severity}">${f.severity}</span></td>
        <td>${f.title}</td>
        <td class="mono" title="${f.address}">${f.address}</td>
        <td>${f.rtype}</td>
        <td>${f.framework}</td>
        <td class="mono">${f.source}</td>`;
      tb.appendChild(tr);
    }
  }

  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  async function toggleDetail(row) {
    const nxt = row.nextElementSibling;
    if (nxt && nxt.classList.contains("detail-row")) {
      nxt.remove(); row.querySelector(".expander").textContent = "▸"; return;
    }
    document.querySelectorAll(".detail-row").forEach((r) => r.remove());
    document.querySelectorAll(".expander").forEach((e) => (e.textContent = "▸"));
    const f = await (await api(`/api/findings/${row.dataset.id}`)).json();
    const tr = document.createElement("tr");
    tr.className = "detail-row";
    tr.innerHTML = `<td colspan="7"><div class="detail-body">
      <div><span class="lbl">Detail</span><div>${esc(f.detail)}</div></div>
      <div class="remediation"><span class="lbl">Remediation</span>
        <div><code>${esc(f.remediation)}</code></div></div>
    </div></td>`;
    row.after(tr);
    row.querySelector(".expander").textContent = "▾";
  }

  $("#file-input").addEventListener("change", (e) =>
    ($("#file-name").textContent = e.target.files[0]?.name || "Choose IaC file…"));

  $("#upload-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = $("#file-input").files[0];
    if (!file) return toast("Pick an IaC file first.", true);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("format", $("#format-select").value);
    try {
      const b = await (await api("/api/ingest", { method: "POST", body: fd })).json();
      toast(`Scanned ${b.source}: ${b.finding_count} findings, risk ${b.risk_score} (grade ${b.grade}).`);
      await refresh();
    } catch (err) { toast("Scan failed: " + err.message, true); }
  });

  ["filter-severity", "filter-rtype"].forEach((id) =>
    $("#" + id).addEventListener("change", () => loadFindings().catch((e) => toast(e.message, true))));

  document.addEventListener("click", (e) => {
    const row = e.target.closest("tr.f-row");
    if (row) toggleDetail(row).catch((err) => toast(err.message, true));
  });

  async function refresh() {
    await Promise.all([loadSummary(), loadFindings()]);
  }
  refresh().catch((err) => toast("Failed to load: " + err.message, true));
})();

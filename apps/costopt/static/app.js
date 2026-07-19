/* CostOpt dashboard */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const root = document.documentElement;
  let charts = {};

  // ---------- theme ----------
  const savedTheme = localStorage.getItem("costopt-theme");
  if (savedTheme) root.dataset.theme = savedTheme;

  $("#btn-theme").addEventListener("click", () => {
    root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("costopt-theme", root.dataset.theme);
    refresh(); // re-render charts with new ink/series tokens
  });

  const cssVar = (name) =>
    getComputedStyle(root).getPropertyValue(name).trim();

  // ---------- toast ----------
  let toastTimer;
  function toast(msg, isError = false) {
    const el = $("#toast");
    el.textContent = msg;
    el.className = "show" + (isError ? " error" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (el.className = ""), 4000);
  }

  // ---------- API with optional key auth ----------
  async function api(path, opts = {}) {
    const key = localStorage.getItem("costopt-api-key");
    if (key) {
      opts.headers = { ...(opts.headers || {}), "X-API-Key": key };
    }
    const res = await fetch(path, opts);
    if (res.status === 401) {
      const entered = prompt("This CostOpt instance requires an API key (viewer or operator):");
      if (entered) {
        localStorage.setItem("costopt-api-key", entered);
        return api(path, opts);
      }
    }
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail || body.error?.message || detail;
        if (typeof detail === "object") detail = JSON.stringify(detail);
      } catch { /* keep statusText */ }
      throw new Error(detail);
    }
    return res;
  }

  const fmtUSD = (v) =>
    "$" + Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  // ---------- charts ----------
  function renderCharts(summary, trends) {
    const ink2 = cssVar("--ink-2");
    const grid = cssVar("--grid");
    const s1 = cssVar("--series-1"), s2 = cssVar("--series-2"),
          s3 = cssVar("--series-3"), s4 = cssVar("--sev-med");
    Object.values(charts).forEach((c) => c.destroy());
    charts = {};
    Chart.defaults.color = ink2;
    Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';

    const catOrder = ["storage", "compute", "network", "governance"];
    const catColors = { storage: s1, compute: s2, network: s3, governance: s4 };
    const catLabels = catOrder.filter((c) => c in summary.by_category);
    charts.category = new Chart($("#chart-category"), {
      type: "doughnut",
      data: {
        labels: catLabels,
        datasets: [{
          data: catLabels.map((c) => summary.by_category[c]),
          backgroundColor: catLabels.map((c) => catColors[c]),
          borderWidth: 2,
          borderColor: cssVar("--glass-border"),
        }],
      },
      options: {
        maintainAspectRatio: false, cutout: "62%",
        plugins: {
          legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
          tooltip: { callbacks: { label: (c) => ` ${c.label}: ${fmtUSD(c.parsed)}/mo` } },
        },
      },
    });

    const provOrder = ["aws", "azure", "gcp"].filter((p) => p in summary.by_provider);
    charts.provider = new Chart($("#chart-provider"), {
      type: "bar",
      data: {
        labels: provOrder.map((p) => p.toUpperCase()),
        datasets: [{
          data: provOrder.map((p) => summary.by_provider[p]),
          backgroundColor: [s1, s2, s3].slice(0, provOrder.length),
          borderRadius: 4, maxBarThickness: 72,
        }],
      },
      options: {
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (c) => ` ${fmtUSD(c.parsed.y)}/mo` } },
        },
        scales: {
          x: { grid: { display: false }, border: { color: grid } },
          y: { grid: { color: grid }, border: { display: false },
               ticks: { callback: (v) => "$" + v } },
        },
      },
    });

    const periods = trends.periods || [];
    charts.months = new Chart($("#chart-months"), {
      type: "bar",
      data: {
        labels: periods.map((p) => p.period),
        datasets: [{
          data: periods.map((p) => p.waste),
          backgroundColor: s1, borderRadius: 4, maxBarThickness: 72,
        }],
      },
      options: {
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: {
            label: (c) => ` ${fmtUSD(c.parsed.y)}/mo waste, ` +
                          `${periods[c.dataIndex].findings} findings` } },
        },
        scales: {
          x: { grid: { display: false }, border: { color: grid } },
          y: { grid: { color: grid }, border: { display: false },
               ticks: { callback: (v) => "$" + v } },
        },
      },
    });

    const trend = summary.scan_trend;
    charts.trend = new Chart($("#chart-trend"), {
      type: "line",
      data: {
        labels: trend.map((t) => "#" + t.scan_id),
        datasets: [{
          label: "Est. monthly savings",
          data: trend.map((t) => t.total_savings),
          borderColor: s1, borderWidth: 2,
          pointRadius: 4, pointBackgroundColor: s1,
          tension: 0.25, fill: false,
        }],
      },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (c) => ` ${fmtUSD(c.parsed.y)}/mo identified` } },
        },
        scales: {
          x: { grid: { display: false }, border: { color: grid }, title: { display: true, text: "scan" } },
          y: { grid: { color: grid }, border: { display: false },
               ticks: { callback: (v) => "$" + v } },
        },
      },
    });
  }

  function fillList(sel, entries, emptyMsg) {
    const ol = $(sel);
    ol.innerHTML = "";
    if (!entries.length) {
      ol.innerHTML = `<li class="empty">${emptyMsg}</li>`;
      return;
    }
    for (const [label, amount] of entries) {
      const li = document.createElement("li");
      li.innerHTML = `<span class="rid mono" title="${label}">${label}</span>
                      <span class="amt">${fmtUSD(amount)}/mo</span>`;
      ol.appendChild(li);
    }
  }

  // ---------- summary ----------
  async function loadSummary() {
    const [summary, trends] = await Promise.all([
      (await api("/api/summary")).json(),
      (await api("/api/trends")).json(),
    ]);
    $("#tile-waste").textContent = fmtUSD(summary.total_monthly_waste) + "/mo";
    $("#tile-open").textContent = summary.open_findings;
    $("#tile-resources").textContent = summary.resources_analyzed;
    $("#tile-annual").textContent = fmtUSD(summary.potential_annual_savings);
    $("#tile-realized").textContent = fmtUSD(summary.realized_monthly_savings) + "/mo";
    fillList("#top-offenders",
             summary.top_offenders.map((o) => [o.resource_id, o.est_monthly_savings]),
             "No data yet — ingest an export and run analysis.");
    fillList("#by-owner", Object.entries(summary.by_owner), "No data yet.");
    renderCharts(summary, trends);
  }

  // ---------- findings table ----------
  const RULE_LABELS = {
    unattached_disk: "Unattached disk", idle_vm: "Idle VM",
    orphaned_ip: "Orphaned IP", old_snapshot: "Old snapshot",
    oversized_vm: "Oversized VM", idle_load_balancer: "Idle LB",
    unused_nat_gateway: "Unused NAT gw", aged_stopped_vm: "Aged stopped VM",
    untagged_resource: "Untagged",
  };

  async function loadFindings() {
    const params = new URLSearchParams();
    if ($("#filter-provider").value) params.set("provider", $("#filter-provider").value);
    if ($("#filter-rule").value) params.set("rule", $("#filter-rule").value);
    if ($("#filter-status").value) params.set("status", $("#filter-status").value);
    const rows = await (await api("/api/findings?" + params)).json();
    const tbody = $("#findings-table tbody");
    tbody.innerHTML = "";
    if (!rows.length) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="10">No findings match — ingest a billing export, then run analysis.</td></tr>';
      return;
    }
    for (const f of rows) {
      const tr = document.createElement("tr");
      tr.className = "f-row";
      tr.dataset.id = f.id;
      tr.innerHTML = `
        <td class="expander">▸</td>
        <td><span class="badge ${f.severity}">${f.severity}</span></td>
        <td>${RULE_LABELS[f.rule] || f.rule}</td>
        <td class="mono" title="${f.resource_id}">${shorten(f.resource_id)}</td>
        <td>${f.provider.toUpperCase()}</td>
        <td>${f.owner || "—"}</td>
        <td>${f.region}</td>
        <td class="num">${fmtUSD(f.est_monthly_savings)}</td>
        <td><span class="badge st-${f.status}">${f.status}</span></td>
        <td class="row-actions">
          <button class="glass-btn small act-dismiss" data-id="${f.id}">Dismiss</button>
          <button class="glass-btn small act-done" data-id="${f.id}">Remediated</button>
        </td>`;
      tbody.appendChild(tr);
    }
  }

  const shorten = (s) => (s.length > 38 ? "…" + s.slice(-36) : s);

  async function toggleDetail(row) {
    const next = row.nextElementSibling;
    if (next && next.classList.contains("detail-row")) {
      next.remove();
      row.querySelector(".expander").textContent = "▸";
      return;
    }
    document.querySelectorAll(".detail-row").forEach((r) => r.remove());
    document.querySelectorAll(".expander").forEach((e) => (e.textContent = "▸"));
    const id = row.dataset.id;
    const plan = await (await api(`/api/findings/${id}/remediation`)).json();
    const tr = document.createElement("tr");
    tr.className = "detail-row";
    const steps = plan.steps.map((s) => `
      <div class="rem-step ${s.destructive ? "destructive" : ""}">
        <p class="rem-intent">${s.order}. ${s.intent} ${s.destructive ? '<span class="danger">⚠ destructive</span>' : ""}</p>
        <div class="codeline"><code>${escapeHtml(s.cli)}</code>
          <button class="glass-btn small btn-copy" data-cmd="${encodeURIComponent(s.cli)}">Copy</button></div>
        <details class="sdk"><summary>SDK equivalent (Python)</summary><pre>${escapeHtml(s.sdk_code)}</pre></details>
      </div>`).join("");
    tr.innerHTML = `<td colspan="10"><div class="rem-steps">${steps}
      <div class="exec-actions">
        <button class="glass-btn small act-dryrun" data-id="${id}">▶ Dry-run (simulated)</button>
        <button class="glass-btn small act-execute" data-id="${id}">⚡ Approve &amp; execute (simulated)</button>
      </div>
      <div class="exec-output" id="exec-output-${id}" hidden></div>
    </div></td>`;
    row.after(tr);
    row.querySelector(".expander").textContent = "▾";
  }

  const escapeHtml = (s) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  async function runExecution(id, dryRun) {
    if (!dryRun && !confirm("Approve simulated execution? The destructive commands "
                            + "will be echoed by the simulated executor and the "
                            + "finding will be marked remediated.")) return;
    const body = { dry_run: dryRun, approve: !dryRun };
    const result = await (await api(`/api/findings/${id}/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })).json();
    const out = $(`#exec-output-${id}`);
    if (out) {
      out.hidden = false;
      out.textContent = result.output;
    }
    toast(dryRun ? "Dry-run complete — no changes made."
                 : `Executed (simulated) — finding #${id} marked remediated.`);
    if (!dryRun) await refresh();
  }

  // ---------- settings modal ----------
  async function openSettings() {
    const [p, sch] = await Promise.all([
      (await api("/api/policies")).json(),
      (await api("/api/schedule")).json(),
    ]);
    $("#pol-retention").value = p.snapshot_retention_days;
    $("#pol-idlecpu").value = p.cpu_idle_threshold_pct;
    $("#pol-rightsize").value = p.vm_rightsize_cpu_pct;
    $("#pol-stoppedage").value = p.stopped_vm_age_days;
    $("#pol-untagged").value = p.untagged_min_cost_usd;
    $("#sch-enabled").checked = sch.enabled;
    $("#sch-interval").value = sch.interval_minutes;
    $("#sch-webhook").value = sch.webhook_url;
    $("#settings-modal").hidden = false;
  }

  async function saveSettings() {
    try {
      await api("/api/policies", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          snapshot_retention_days: Number($("#pol-retention").value),
          cpu_idle_threshold_pct: Number($("#pol-idlecpu").value),
          vm_rightsize_cpu_pct: Number($("#pol-rightsize").value),
          stopped_vm_age_days: Number($("#pol-stoppedage").value),
          untagged_min_cost_usd: Number($("#pol-untagged").value),
        }),
      });
      await api("/api/schedule", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: $("#sch-enabled").checked,
          interval_minutes: Number($("#sch-interval").value) || 60,
          webhook_url: $("#sch-webhook").value,
        }),
      });
      $("#settings-modal").hidden = true;
      toast("Policies & schedule saved. Re-run analysis to apply new thresholds.");
    } catch (err) { toast("Save failed: " + err.message, true); }
  }

  // ---------- events ----------
  $("#file-input").addEventListener("change", (e) => {
    $("#file-name").textContent = e.target.files[0]?.name || "Choose export…";
  });

  $("#upload-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = $("#file-input").files[0];
    if (!file) return toast("Pick a billing export file first.", true);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("provider", $("#provider-select").value);
    try {
      const body = await (await api("/api/ingest", { method: "POST", body: fd })).json();
      if (body.duplicate) toast("Duplicate file — already ingested, nothing changed.");
      else toast(`Ingested ${body.rows_ok} resources (${body.rows_failed} bad rows). Now run analysis.`);
      await refresh();
    } catch (err) { toast("Ingest failed: " + err.message, true); }
  });

  $("#btn-analyze").addEventListener("click", async () => {
    try {
      const body = await (await api("/api/analyze", { method: "POST" })).json();
      toast(`Scan #${body.scan_id}: ${body.open_findings} open findings, ` +
            `${fmtUSD(body.total_est_monthly_savings)}/mo potential savings.`);
      await refresh();
    } catch (err) { toast("Analysis failed: " + err.message, true); }
  });

  $("#btn-settings").addEventListener("click", () =>
    openSettings().catch((e) => toast(e.message, true)));
  $("#btn-settings-close").addEventListener("click", () =>
    ($("#settings-modal").hidden = true));
  $("#btn-settings-save").addEventListener("click", saveSettings);

  ["filter-provider", "filter-rule", "filter-status"].forEach((id) =>
    $("#" + id).addEventListener("change", () => loadFindings().catch((e) => toast(e.message, true))));

  document.addEventListener("click", async (e) => {
    const copyBtn = e.target.closest(".btn-copy");
    if (copyBtn) {
      e.stopPropagation();
      await navigator.clipboard.writeText(decodeURIComponent(copyBtn.dataset.cmd));
      copyBtn.textContent = "Copied!";
      setTimeout(() => (copyBtn.textContent = "Copy"), 1500);
      return;
    }
    const dryBtn = e.target.closest(".act-dryrun");
    const execBtn = e.target.closest(".act-execute");
    if (dryBtn || execBtn) {
      e.stopPropagation();
      runExecution((dryBtn || execBtn).dataset.id, Boolean(dryBtn))
        .catch((err) => toast(err.message, true));
      return;
    }
    const dismiss = e.target.closest(".act-dismiss");
    const done = e.target.closest(".act-done");
    if (dismiss || done) {
      e.stopPropagation();
      const id = (dismiss || done).dataset.id;
      const status = dismiss ? "dismissed" : "remediated";
      try {
        await api(`/api/findings/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status }),
        });
        toast(`Finding #${id} marked ${status}.`);
        await refresh();
      } catch (err) { toast(err.message, true); }
      return;
    }
    const row = e.target.closest("tr.f-row");
    if (row) toggleDetail(row).catch((err) => toast(err.message, true));
  });

  async function refresh() {
    await Promise.all([loadSummary(), loadFindings()]);
  }

  refresh().catch((err) => toast("Failed to load: " + err.message, true));
})();

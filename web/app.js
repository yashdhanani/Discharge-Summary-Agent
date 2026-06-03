const state = {
  runs: [],
  selectedRunId: null,
  activeTab: "draft",
  loading: false,
};

const els = {
  runTask: document.getElementById("runTask"),
  runSample: document.getElementById("runSample"),
  refresh: document.getElementById("refresh"),
  runList: document.getElementById("runList"),
  content: document.getElementById("content"),
  healthDot: document.getElementById("healthDot"),
  healthText: document.getElementById("healthText"),
  toast: document.getElementById("toast"),
  metricEvidence: document.getElementById("metricEvidence"),
  metricMissing: document.getElementById("metricMissing"),
  metricMeds: document.getElementById("metricMeds"),
  metricFlags: document.getElementById("metricFlags"),
  metricConflicts: document.getElementById("metricConflicts"),
  tabs: Array.from(document.querySelectorAll(".tab")),
};

els.tabs.forEach((tab) => {
  tab.addEventListener("click", () => activateTab(tab.dataset.tab));
});

els.runTask.addEventListener("click", () => runJob("task"));
els.runSample.addEventListener("click", () => runJob("sample"));
els.refresh.addEventListener("click", () => refresh());

activateTab(state.activeTab, false);
refresh();

async function refresh() {
  try {
    const health = await getJson("/api/health");
    els.healthDot.classList.toggle("ok", health.status === "ok");
    els.healthText.textContent = `${health.runs} run${health.runs === 1 ? "" : "s"} ready`;

    const payload = await getJson("/api/runs");
    state.runs = payload.runs || [];
    reconcileSelectedRun();
    renderRuns();
    renderMetrics();
    await renderActiveArtifact();
  } catch (error) {
    els.healthDot.classList.remove("ok");
    els.healthText.textContent = "Backend unavailable";
    renderEmptyDashboard("Backend unavailable");
    showToast(error.message);
  }
}

async function runJob(mode) {
  setLoading(true);
  try {
    const result = await postJson("/api/run", { mode, learning: true, max_steps: 10 });
    state.runs = result.available_runs || [];
    state.selectedRunId = inferRunIdFromResult(result);
    reconcileSelectedRun();
    showToast(mode === "task" ? "Provided patient run complete" : "Sample batch run complete");
    renderRuns();
    renderMetrics();
    await renderActiveArtifact();
  } catch (error) {
    showToast(error.message);
  } finally {
    setLoading(false);
  }
}

function inferRunIdFromResult(result) {
  if (result.mode === "task") return "provided";
  const firstOutput = result.runs?.[0]?.output || "";
  const lastSegment = firstOutput.split(/[\\/]/).filter(Boolean).pop();
  if (lastSegment) return `sample/${lastSegment}`;
  return state.runs.find((run) => run.id.startsWith("sample/"))?.id || state.runs[0]?.id || null;
}

function reconcileSelectedRun() {
  if (!state.runs.length) {
    state.selectedRunId = null;
    return;
  }
  if (!state.selectedRunId || !state.runs.some((run) => run.id === state.selectedRunId)) {
    state.selectedRunId = state.runs[0].id;
  }
}

function activateTab(tabName, shouldRender = true) {
  state.activeTab = tabName;
  els.tabs.forEach((tab) => {
    const active = tab.dataset.tab === tabName;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
    tab.setAttribute("tabindex", active ? "0" : "-1");
  });
  if (shouldRender) renderActiveArtifact();
}

function renderRuns() {
  if (!state.runs.length) {
    els.runList.innerHTML = `<div class="empty-state compact">No runs yet</div>`;
    return;
  }

  els.runList.innerHTML = state.runs.map(renderRunCard).join("");
  document.querySelectorAll(".run-item").forEach((item) => {
    item.addEventListener("click", () => {
      state.selectedRunId = item.dataset.run;
      renderRuns();
      renderMetrics();
      renderActiveArtifact();
    });
  });
}

function renderRunCard(run) {
  const quality = run.quality || {};
  const required = quality.required_fields || {};
  const meds = quality.medications || {};
  const flags = quality.clinician_review_flags || [];
  const missing = required.missing || [];
  const conflicts = quality.conflicts_count || 0;
  const needsReview = flags.length > 0 || missing.length > 0 || conflicts > 0;
  const statusClass = needsReview ? "review" : "clean";
  const statusLabel = needsReview ? "Review" : "Clean";
  const active = run.id === state.selectedRunId;

  return `
    <button class="run-item ${active ? "active" : ""}" data-run="${escapeHtml(run.id)}" type="button" aria-pressed="${active}">
      <span class="run-row">
        <span class="run-title">${escapeHtml(run.label)}</span>
        <span class="status-pill ${statusClass}">${statusLabel}</span>
      </span>
      <span class="run-sub">${formatCoverage(required.evidence_coverage)} evidence | ${meds.discharge_count ?? 0} meds</span>
      <span class="run-chips">
        <span class="mini-chip">Missing ${missing.length}</span>
        <span class="mini-chip">Flags ${flags.length}</span>
        <span class="mini-chip">Conflicts ${conflicts}</span>
      </span>
    </button>
  `;
}

function renderMetrics() {
  const run = selectedRun();
  if (!run) {
    els.metricEvidence.textContent = "--";
    els.metricMissing.textContent = "--";
    els.metricMeds.textContent = "--";
    els.metricFlags.textContent = "--";
    els.metricConflicts.textContent = "--";
    return;
  }

  const quality = run.quality || {};
  const required = quality.required_fields || {};
  const meds = quality.medications || {};
  els.metricEvidence.textContent = formatCoverage(required.evidence_coverage);
  els.metricMissing.textContent = (required.missing || []).length;
  els.metricMeds.textContent = meds.discharge_count ?? "--";
  els.metricFlags.textContent = (quality.clinician_review_flags || []).length;
  els.metricConflicts.textContent = quality.conflicts_count ?? "--";
}

async function renderActiveArtifact() {
  if (!state.selectedRunId) {
    renderEmptyDashboard("Run the agent to view artifacts");
    return;
  }

  els.content.innerHTML = `<div class="empty-state">Loading ${escapeHtml(state.activeTab)}</div>`;
  try {
    if (state.activeTab === "draft") {
      const artifact = await artifactJson("draft");
      els.content.innerHTML = `<article class="markdown">${markdownToHtml(artifact.content || "")}</article>`;
    } else if (state.activeTab === "trace") {
      const artifact = await artifactJson("trace");
      renderTrace(artifact.content || []);
    } else if (state.activeTab === "quality") {
      const artifact = await artifactJson("quality");
      renderQuality(artifact.content || {});
    } else if (state.activeTab === "learning") {
      const artifact = await artifactJson("learning");
      renderLearning(artifact.content || {});
    } else {
      const artifact = await artifactJson("structured");
      els.content.innerHTML = `<pre>${escapeHtml(JSON.stringify(artifact.content, null, 2))}</pre>`;
    }
  } catch (error) {
    els.content.innerHTML = `<div class="empty-state error">${escapeHtml(error.message)}</div>`;
  }
}

function renderTrace(trace) {
  if (!Array.isArray(trace) || !trace.length) {
    els.content.innerHTML = `<div class="empty-state">No trace steps available</div>`;
    return;
  }

  els.content.innerHTML = `
    <div class="trace-list">
      ${trace
        .map(
          (step) => `
            <section class="trace-step">
              <div class="trace-index">${String(step.step ?? "").padStart(2, "0")}</div>
              <div class="trace-body">
                <div class="trace-head">
                  <div>
                    <span class="trace-label">Action</span>
                    <strong>${escapeHtml(step.tool_or_action || "unknown")}</strong>
                  </div>
                  <span class="badge ok">${escapeHtml(step.next_decision || "complete")}</span>
                </div>
                <p><strong>Reasoning:</strong> ${escapeHtml(step.reasoning || "")}</p>
                <p><strong>Result:</strong> ${escapeHtml(step.result || "")}</p>
                <details>
                  <summary>Inputs</summary>
                  <pre>${escapeHtml(JSON.stringify(step.inputs || {}, null, 2))}</pre>
                </details>
              </div>
            </section>
          `
        )
        .join("")}
    </div>
  `;
}

function renderQuality(quality) {
  const required = quality.required_fields || {};
  const meds = quality.medications || {};
  const flags = quality.clinician_review_flags || [];
  const missing = required.missing || [];
  const uncertain = required.uncertain || [];

  els.content.innerHTML = `
    <div class="quality-grid">
      ${qualityBlock("Source", [
        ["Pages read", quality.patient_pages_read],
        ["Characters", formatInteger(quality.extracted_characters)],
        ["Agent steps", quality.agent_steps],
        ["Step cap", quality.step_cap_respected ? "Respected" : "Exceeded"],
      ])}
      ${qualityBlock("Coverage", [
        ["Evidence coverage", formatCoverage(required.evidence_coverage)],
        ["Missing fields", missing.length],
        ["Uncertain fields", uncertain.length],
        ["Evidence-backed", (required.evidence_backed || []).length],
      ])}
      ${qualityBlock("Medications", [
        ["Discharge meds", meds.discharge_count],
        ["Admission/inpatient", meds.admission_or_inpatient_count],
        ["Reconciliation rows", meds.reconciliation_rows],
        ["Reconciliation alerts", meds.reconciliation_alerts],
      ])}
      ${qualityBlock("Safety", [
        ["Pending results", quality.pending_results_count],
        ["Conflicts", quality.conflicts_count],
        ["Safety alerts", quality.safety_alerts_count],
        ["Review flags", flags.length],
      ])}
    </div>

    <div class="review-grid">
      <section>
        <h2>Missing And Uncertain Fields</h2>
        ${renderFieldList("Missing", missing, "No missing required fields.")}
        ${renderFieldList("Uncertain", uncertain, "No uncertain required fields.")}
      </section>
      <section>
        <h2>Clinician Review Flags</h2>
        <ul class="flag-list">
          ${
            flags.length
              ? flags.map((flag) => `<li><span class="flag-type">${flagType(flag)}</span><span>${escapeHtml(cleanFlag(flag))}</span></li>`).join("")
              : `<li class="quiet">No clinician review flags.</li>`
          }
        </ul>
      </section>
    </div>
  `;
}

function renderLearning(learning) {
  const curve = learning.curve || [];
  const before = Number(learning.before_edit_burden);
  const after = Number(learning.after_edit_burden);
  const improvement = Number.isFinite(before) && Number.isFinite(after) ? before - after : null;

  els.content.innerHTML = `
    <div class="chart-wrap">
      <div class="quality-grid">
        ${qualityBlock("Before", [["Edit burden", formatDecimal(before)]])}
        ${qualityBlock("After", [["Edit burden", formatDecimal(after)]])}
        ${qualityBlock("Improvement", [["Edit burden delta", improvement === null ? "n/a" : formatSignedDecimal(improvement)]])}
        ${qualityBlock("Scope", [
          ["Best strategy", learning.best_strategy || "n/a"],
          ["Clinical facts", "unchanged"],
        ])}
      </div>
      <canvas id="learningChart" width="960" height="280" aria-label="Learning curve"></canvas>
      <div class="learning-note">
        ${escapeHtml(learning.mechanism || "Presentation strategy selection")} with reward based on lower simulated edit burden.
      </div>
      <pre>${escapeHtml(JSON.stringify(curve, null, 2))}</pre>
    </div>
  `;
  drawChart(curve);
}

function qualityBlock(title, rows) {
  return `
    <section class="quality-block">
      <h3>${escapeHtml(title)}</h3>
      ${rows
        .map(
          ([label, value]) => `
            <p>
              <span>${escapeHtml(label)}</span>
              <strong>${escapeHtml(value ?? "n/a")}</strong>
            </p>
          `
        )
        .join("")}
    </section>
  `;
}

function renderFieldList(label, items, emptyText) {
  return `
    <div class="field-group">
      <h3>${escapeHtml(label)}</h3>
      ${
        items.length
          ? `<div class="pill-list">${items.map((item) => `<span class="field-pill">${escapeHtml(prettyField(item))}</span>`).join("")}</div>`
          : `<p class="quiet">${escapeHtml(emptyText)}</p>`
      }
    </div>
  `;
}

function drawChart(curve) {
  const canvas = document.getElementById("learningChart");
  if (!canvas || !Array.isArray(curve) || !curve.length) return;

  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const left = 54;
  const right = 28;
  const top = 32;
  const bottom = 42;
  const chartWidth = width - left - right;
  const chartHeight = height - top - bottom;
  const values = curve.map((point) => Number(point.edit_burden)).filter(Number.isFinite);
  if (!values.length) return;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = max - min || 1;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#d8dee9";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#64748b";
  ctx.font = "13px system-ui";

  for (let i = 0; i <= 4; i += 1) {
    const y = top + (i / 4) * chartHeight;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(width - right, y);
    ctx.stroke();
  }

  ctx.fillText("Edit burden", left, 20);
  ctx.fillText(min.toFixed(4), left, height - 14);
  ctx.fillText(max.toFixed(4), width - 90, 24);

  ctx.strokeStyle = "#0f766e";
  ctx.lineWidth = 3;
  ctx.beginPath();
  curve.forEach((point, index) => {
    const value = Number(point.edit_burden);
    if (!Number.isFinite(value)) return;
    const x = left + (index / Math.max(1, curve.length - 1)) * chartWidth;
    const y = top + chartHeight - ((value - min) / spread) * chartHeight;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  curve.forEach((point, index) => {
    const value = Number(point.edit_burden);
    if (!Number.isFinite(value)) return;
    const x = left + (index / Math.max(1, curve.length - 1)) * chartWidth;
    const y = top + chartHeight - ((value - min) / spread) * chartHeight;
    ctx.beginPath();
    ctx.fillStyle = point.strategy === "safety_first" ? "#0f766e" : "#1d4ed8";
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fill();
  });
}

function selectedRun() {
  return state.runs.find((run) => run.id === state.selectedRunId);
}

function artifactJson(artifact) {
  const params = new URLSearchParams({ run_id: state.selectedRunId, artifact });
  return getJson(`/api/artifact?${params.toString()}`);
}

async function getJson(url) {
  const response = await fetch(url);
  return parseJsonResponse(response);
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse(response);
}

async function parseJsonResponse(response) {
  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch (error) {
    throw new Error(text || response.statusText || "Request failed");
  }
  if (!response.ok) throw new Error(payload.error || response.statusText || "Request failed");
  return payload;
}

function markdownToHtml(markdown) {
  const lines = markdown.split("\n");
  let html = "";
  let inList = false;

  lines.forEach((line) => {
    const trimmed = line.trim();
    if (trimmed.startsWith("- ")) {
      if (!inList) {
        html += "<ul>";
        inList = true;
      }
      html += `<li>${escapeHtml(trimmed.slice(2))}</li>`;
      return;
    }
    if (inList) {
      html += "</ul>";
      inList = false;
    }
    if (trimmed.startsWith("### ")) html += `<h3>${escapeHtml(trimmed.slice(4))}</h3>`;
    else if (trimmed.startsWith("## ")) html += `<h2>${escapeHtml(trimmed.slice(3))}</h2>`;
    else if (trimmed.startsWith("# ")) html += `<h1>${escapeHtml(trimmed.slice(2))}</h1>`;
    else if (trimmed.startsWith("Status:")) html += `<p class="draft-status">${escapeHtml(trimmed)}</p>`;
    else if (trimmed) html += `<p>${escapeHtml(trimmed)}</p>`;
  });
  if (inList) html += "</ul>";
  return html;
}

function renderEmptyDashboard(message) {
  els.content.innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
  renderMetrics();
  renderRuns();
}

function setLoading(value) {
  state.loading = value;
  document.body.classList.toggle("is-loading", value);
  [els.runTask, els.runSample, els.refresh].forEach((button) => {
    button.disabled = value;
    button.setAttribute("aria-busy", String(value));
  });
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.setTimeout(() => els.toast.classList.remove("show"), 3000);
}

function formatCoverage(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  return `${Math.round(number * 100)}%`;
}

function formatInteger(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "n/a";
  return number.toLocaleString();
}

function formatDecimal(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "n/a";
  return number.toFixed(4);
}

function formatSignedDecimal(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "n/a";
  return `${number >= 0 ? "+" : ""}${number.toFixed(4)}`;
}

function prettyField(value) {
  return String(value || "").replaceAll("_", " ");
}

function flagType(flag) {
  const text = String(flag || "").toLowerCase();
  if (text.includes("medication")) return "Med";
  if (text.includes("diagnosis") || text.includes("conflict")) return "Conflict";
  if (text.includes("missing") || text.includes("uncertain")) return "Field";
  if (text.includes("safety") || text.includes("qt") || text.includes("cns")) return "Safety";
  return "Review";
}

function cleanFlag(flag) {
  return String(flag || "").replace(/^CLINICIAN_REVIEW:\s*/i, "");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

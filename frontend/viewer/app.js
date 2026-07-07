const API_BASE = "/viewer-api";
const launchParams = new URLSearchParams(window.location.search);

const state = {
  sessionId: null,
  filename: null,
  variable: null,
  plotMode: "year",
  year: null,
  month: "all",
  day: "all",
  resolution: "5min",
  minCoverage: 80,
  years: [],
  monthsByYear: {},
  daysByMonth: {},
  loading: false,
  progressTimer: null,
  progressValue: 0,
  webgl: null,
  themeMode: localStorage.getItem("agender.viewer.theme") || "system",
};

const el = {
  mainView: document.getElementById("mainView"),
  themeModeInputs: Array.from(document.querySelectorAll('input[name="themeMode"]')),
  fileName: document.getElementById("fileName"),
  fileProgress: document.getElementById("fileProgress"),
  fileProgressLabel: document.getElementById("fileProgressLabel"),
  fileProgressPercent: document.getElementById("fileProgressPercent"),
  fileProgressBar: document.getElementById("fileProgressBar"),
  variableTabsShell: document.getElementById("variableTabsShell"),
  variableTabs: document.getElementById("variableTabs"),
  tabScrollLeftBtn: document.getElementById("tabScrollLeftBtn"),
  tabScrollRightBtn: document.getElementById("tabScrollRightBtn"),
  plotModeInputs: Array.from(document.querySelectorAll('input[name="plotMode"]')),
  yearControl: document.getElementById("yearControl"),
  yearSelect: document.getElementById("yearSelect"),
  monthSelect: document.getElementById("monthSelect"),
  daySelect: document.getElementById("daySelect"),
  resolutionSelect: document.getElementById("resolutionSelect"),
  coverageInput: document.getElementById("coverageInput"),
  chart: document.getElementById("chart"),
  chartTitle: document.getElementById("chartTitle"),
  appStatus: document.getElementById("appStatus"),
  statusText: document.getElementById("statusText"),
  progressPercent: document.getElementById("progressPercent"),
  loadProgress: document.getElementById("loadProgress"),
  loadProgressBar: document.getElementById("loadProgressBar"),
  statSummary: document.getElementById("statSummary"),
  exportCsvBtn: document.getElementById("exportCsvBtn"),
  exportParquetBtn: document.getElementById("exportParquetBtn"),
  statTotal: document.getElementById("statTotal"),
  statRecords: document.getElementById("statRecords"),
  statMissing: document.getElementById("statMissing"),
  statCompleteness: document.getElementById("statCompleteness"),
};

function setStatus(message) {
  el.statusText.textContent = message;
}

function setLoadProgress(value, message = null) {
  const percent = Math.max(0, Math.min(100, Math.round(value)));
  state.progressValue = percent;
  el.progressPercent.hidden = false;
  el.loadProgress.hidden = false;
  el.progressPercent.textContent = `${percent}%`;
  el.loadProgressBar.style.width = `${percent}%`;
  el.fileProgress.hidden = false;
  el.fileProgressPercent.textContent = `${percent}%`;
  el.fileProgressBar.style.width = `${percent}%`;
  if (message) {
    el.fileProgressLabel.textContent = message;
  }
  if (message) setStatus(message);
}

function stopProgressTimer() {
  if (state.progressTimer) {
    clearInterval(state.progressTimer);
    state.progressTimer = null;
  }
}

function startProcessingProgress(fileName) {
  stopProgressTimer();
  state.progressTimer = setInterval(() => {
    if (!state.loading || state.progressValue >= 95) return;
    const next = state.progressValue + Math.max(1, Math.round((95 - state.progressValue) * 0.08));
    setLoadProgress(Math.min(next, 95), `Procesando ${fileName}...`);
  }, 260);
}

function finishLoadProgress(message) {
  stopProgressTimer();
  setLoadProgress(100, message);
  setTimeout(() => {
    if (state.loading) return;
    el.progressPercent.hidden = true;
    el.loadProgress.hidden = true;
    el.loadProgressBar.style.width = "0%";
    el.fileProgress.hidden = true;
    el.fileProgressBar.style.width = "0%";
  }, 1800);
}

function failLoadProgress(message) {
  stopProgressTimer();
  setStatus(message);
  el.progressPercent.hidden = true;
  el.loadProgress.hidden = true;
  el.loadProgressBar.style.width = "0%";
  el.fileProgress.hidden = true;
  el.fileProgressBar.style.width = "0%";
}

function systemPrefersDark() {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

function resolvedTheme() {
  if (state.themeMode === "system") {
    return systemPrefersDark() ? "dark" : "light";
  }
  return state.themeMode;
}

function applyTheme() {
  document.documentElement.dataset.theme = resolvedTheme();
  el.themeModeInputs.forEach((input) => {
    input.checked = input.value === state.themeMode;
  });
}

function setThemeMode(mode) {
  state.themeMode = mode;
  localStorage.setItem("agender.viewer.theme", mode);
  applyTheme();
}

function formatNumber(value) {
  return new Intl.NumberFormat("es-CO").format(value ?? 0);
}

function setStats(stats) {
  el.statTotal.textContent = formatNumber(stats.total);
  el.statRecords.textContent = formatNumber(stats.records ?? stats.active);
  el.statMissing.textContent = formatNumber(stats.missing);
  el.statCompleteness.textContent = `${Number(stats.completeness ?? 0).toFixed(2)}%`;
  el.statSummary.textContent = `Total: ${formatNumber(stats.total)} | Registros: ${formatNumber(
    stats.records ?? stats.active,
  )} | Vacíos: ${formatNumber(stats.missing)} | Completitud: ${Number(stats.completeness ?? 0).toFixed(2)}%`;
}

function setControlsEnabled(enabled) {
  [
    el.yearSelect,
    el.monthSelect,
    el.daySelect,
    el.resolutionSelect,
    el.coverageInput,
    el.exportCsvBtn,
    el.exportParquetBtn,
  ].forEach((node) => {
    node.disabled = !enabled;
  });
  el.plotModeInputs.forEach((node) => {
    node.disabled = !enabled;
  });
  updatePeriodControls();
}

function renderVariableTabs(variables) {
  el.variableTabs.innerHTML = "";
  if (!variables.length) {
    el.variableTabs.classList.add("empty");
    updateTabScroller();
    return;
  }

  el.variableTabs.classList.remove("empty");
  variables.forEach((variable) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "variable-tab";
    button.textContent = variable;
    button.dataset.variable = variable;
    button.setAttribute("aria-pressed", String(variable === state.variable));
    button.addEventListener("click", async () => {
      if (state.variable === variable || state.loading) return;
      state.variable = variable;
      updateActiveTab();
      await loadSeries();
    });
    el.variableTabs.appendChild(button);
  });
  requestAnimationFrame(() => {
    updateActiveTab();
    updateTabScroller();
  });
}

function updateActiveTab() {
  el.variableTabs.querySelectorAll(".variable-tab").forEach((tab) => {
    const active = tab.dataset.variable === state.variable;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-pressed", String(active));
    if (active) {
      tab.scrollIntoView({ block: "nearest", inline: "center" });
    }
  });
  updateTabScroller();
}

function updateTabScroller() {
  const maxScrollLeft = Math.max(0, el.variableTabs.scrollWidth - el.variableTabs.clientWidth);
  const canScrollLeft = el.variableTabs.scrollLeft > 2;
  const canScrollRight = el.variableTabs.scrollLeft < maxScrollLeft - 2;

  el.variableTabsShell.classList.toggle("can-scroll-left", canScrollLeft);
  el.variableTabsShell.classList.toggle("can-scroll-right", canScrollRight);
  el.tabScrollLeftBtn.disabled = !canScrollLeft;
  el.tabScrollRightBtn.disabled = !canScrollRight;
}

function scrollVariableTabs(direction) {
  const distance = Math.max(240, Math.round(el.variableTabs.clientWidth * 0.72));
  el.variableTabs.scrollBy({ left: direction * distance, behavior: "smooth" });
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch (error) {
    throw new Error("No se pudo conectar con el módulo Viewer.");
  }
  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch {
      // Keep the HTTP status text.
    }
    throw new Error(message);
  }
  return response;
}

async function waitForApi() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      await api("/api/health");
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  setStatus("API local no disponible.");
}

function fillSelect(select, values) {
  select.innerHTML = "";
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
}

function formatMonth(month) {
  const date = new Date(2024, Number(month) - 1, 1);
  const label = new Intl.DateTimeFormat("es-CO", { month: "long" }).format(date);
  return `${String(month).padStart(2, "0")} - ${label.charAt(0).toUpperCase()}${label.slice(1)}`;
}

function fillPeriodSelect(select, values, formatter = (value) => value) {
  select.innerHTML = "";
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = formatter(value);
    select.appendChild(option);
  });
}

function monthKey(year, month) {
  return `${year}-${String(month).padStart(2, "0")}`;
}

function availableMonths() {
  if (state.plotMode === "year") {
    return state.monthsByYear[String(state.year)] || [];
  }

  const months = new Set();
  Object.values(state.monthsByYear).forEach((yearMonths) => {
    yearMonths.forEach((month) => months.add(month));
  });
  return Array.from(months).sort((a, b) => a - b);
}

function availableDays() {
  if (state.month === "all") return [];

  const days = new Set();
  if (state.plotMode === "year") {
    (state.daysByMonth[monthKey(state.year, state.month)] || []).forEach((day) => days.add(day));
  } else {
    state.years.forEach((year) => {
      (state.daysByMonth[monthKey(year, state.month)] || []).forEach((day) => days.add(day));
    });
  }
  return Array.from(days).sort((a, b) => a - b);
}

function syncPeriodOptions() {
  fillPeriodSelect(el.yearSelect, state.years);
  if (state.year) el.yearSelect.value = state.year;

  const months = availableMonths();
  if (state.month !== "all" && !months.includes(state.month)) {
    state.month = "all";
  }
  fillPeriodSelect(el.monthSelect, ["all", ...months], (month) => (month === "all" ? "Todos los meses" : formatMonth(month)));
  el.monthSelect.value = state.month;

  const days = availableDays();
  if (state.day !== "all" && !days.includes(state.day)) {
    state.day = "all";
  }
  fillPeriodSelect(el.daySelect, ["all", ...days], (day) => (day === "all" ? "Todos los días" : String(day).padStart(2, "0")));
  el.daySelect.value = state.day;
}

function updatePeriodControls() {
  const hasData = Boolean(state.sessionId);
  const needsYear = state.plotMode === "year";
  const annual = state.resolution === "year";
  const monthlyOrAnnual = state.resolution === "month" || annual;

  el.yearControl.classList.toggle("is-hidden", !needsYear);
  el.yearSelect.disabled = !hasData || !needsYear;
  el.monthSelect.disabled = !hasData || annual;
  el.daySelect.disabled = !hasData || state.month === "all" || monthlyOrAnnual;

  el.plotModeInputs.forEach((input) => {
    input.checked = input.value === state.plotMode;
    input.disabled = !hasData;
  });
}

function supportsWebGL() {
  if (state.webgl !== null) return state.webgl;
  const canvas = document.createElement("canvas");
  state.webgl = Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  return state.webgl;
}

async function applyMetadata(metadata) {
  state.sessionId = metadata.session_id;
  state.filename = metadata.filename;
  state.variable = metadata.variables[0];
  state.plotMode = "year";
  state.years = metadata.years;
  state.monthsByYear = metadata.months_by_year || {};
  state.daysByMonth = metadata.days_by_month || {};
  state.year = metadata.years.at(-1);
  state.month = "all";
  state.day = "all";

  el.fileName.textContent = metadata.filename;
  syncPeriodOptions();
  updatePeriodControls();
  renderVariableTabs(metadata.variables);
  setControlsEnabled(true);
  await loadSeries();
  state.loading = false;
  finishLoadProgress(`Archivo cargado: ${metadata.filename}`);
}

async function openStation(station, source) {
  state.loading = true;
  setLoadProgress(8, `Buscando archivos de ${station}...`);
  startProcessingProgress(station);
  const response = await api(`/api/stations/${encodeURIComponent(station)}?source=${encodeURIComponent(source)}`, {
    method: "POST",
  });
  const metadata = await response.json();
  setLoadProgress(96, `Preparando ${metadata.filename}...`);
  await applyMetadata(metadata);
}

function chartLayout(payload) {
  return {
    margin: { l: 64, r: 28, t: 18, b: 54 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    hovermode: "closest",
    dragmode: "zoom",
    showlegend: true,
    legend: { orientation: "h", x: 0, y: 1.02 },
    xaxis: {
      title: "Fecha y hora",
      gridcolor: "#edf1f5",
      rangeslider: { visible: false },
    },
    yaxis: {
      title: payload.variable,
      gridcolor: "#edf1f5",
      zerolinecolor: "#d9e0e7",
    },
  };
}

function periodTitle() {
  const scope = state.plotMode === "all" ? "Todos los años" : `Año: ${state.year}`;
  if (state.month === "all") return scope;

  const monthText = `Mes: ${String(state.month).padStart(2, "0")}`;
  if (state.day === "all") return `${scope} | ${monthText}`;

  return `${scope} | ${monthText} | Día: ${String(state.day).padStart(2, "0")}`;
}

function resolutionLabel() {
  return el.resolutionSelect.options[el.resolutionSelect.selectedIndex]?.textContent || "5 minutos";
}

function statusPeriodText(payload) {
  const scope = state.plotMode === "all" ? "todos los años" : `año ${payload.year}`;
  if (payload.month === null) return scope;
  if (payload.day === null) return `${scope}, mes ${String(payload.month).padStart(2, "0")}`;
  return `${scope}, día ${String(payload.day).padStart(2, "0")} del mes ${String(payload.month).padStart(2, "0")}`;
}

function makeTrace(name, x, y, rowIds, color, coverage = [], available = [], expected = []) {
  return {
    type: supportsWebGL() ? "scattergl" : "scatter",
    mode: "markers",
    name,
    x,
    y,
    customdata: x.map((_, index) => [rowIds[index], coverage[index], available[index], expected[index]]),
    marker: { color, size: 5, opacity: 0.82 },
    hovertemplate: "%{x}<br>Valor: %{y}<br>Cobertura: %{customdata[1]}% (%{customdata[2]}/%{customdata[3]})<extra></extra>",
  };
}

function tracesForPayload(payload) {
  if (state.plotMode !== "all") {
    return [makeTrace(payload.variable, payload.x, payload.y, payload.row_ids, "#0067c0", payload.coverage, payload.available, payload.expected)];
  }

  const colors = ["#0067c0", "#107c10", "#c42b1c", "#8661c5", "#b75c00", "#008575", "#5c2d91"];
  const byYear = new Map();
  payload.x.forEach((timestamp, index) => {
    const year = String(new Date(timestamp).getFullYear());
    if (!byYear.has(year)) byYear.set(year, { x: [], y: [], rowIds: [], coverage: [], available: [], expected: [] });
    const bucket = byYear.get(year);
    bucket.x.push(timestamp);
    bucket.y.push(payload.y[index]);
    bucket.rowIds.push(payload.row_ids[index]);
    bucket.coverage.push(payload.coverage[index]);
    bucket.available.push(payload.available[index]);
    bucket.expected.push(payload.expected[index]);
  });

  return Array.from(byYear.entries()).map(([year, bucket], index) =>
    makeTrace(year, bucket.x, bucket.y, bucket.rowIds, colors[index % colors.length], bucket.coverage, bucket.available, bucket.expected),
  );
}

async function loadSeries() {
  if (!state.sessionId || !state.variable) return;
  syncPeriodOptions();
  updatePeriodControls();
  if (state.plotMode !== "all" && !state.year) return;
  if (state.day !== "all" && state.month === "all") return;

  setStatus(`Consultando ${state.variable}: ${periodTitle()}...`);
  el.chartTitle.textContent = `Variable: ${state.variable} | ${periodTitle()} | ${resolutionLabel()} · n≥${state.minCoverage}%`;
  updateActiveTab();

  const params = new URLSearchParams({
    session_id: state.sessionId,
    variable: state.variable,
    resolution: state.resolution,
    min_coverage: state.minCoverage,
  });
  if (state.plotMode !== "all") params.set("year", state.year);
  if (state.month !== "all") params.set("month", state.month);
  if (state.day !== "all") params.set("day", state.day);

  const response = await api(`/api/data?${params.toString()}`);
  const payload = await response.json();
  const traces = tracesForPayload(payload);

  const config = {
    responsive: true,
    scrollZoom: true,
    displaylogo: false,
    modeBarButtonsToRemove: [
      "toImage",
      "pan2d",
      "select2d",
      "lasso2d",
      "zoomIn2d",
      "zoomOut2d",
      "autoScale2d",
      "hoverClosestCartesian",
      "hoverCompareCartesian",
      "toggleSpikelines",
    ],
  };

  await Plotly.react(el.chart, traces, chartLayout(payload), config);
  setStats(payload.stats);

  const sampleText = ` ${formatNumber(payload.grouped_periods)} períodos: ${formatNumber(payload.accepted_periods)} válidos y ${formatNumber(payload.na_periods)} NA; resolución ${resolutionLabel().toLowerCase()}, cobertura mínima ${state.minCoverage}%, ${payload.aggregation}.`;
  const renderText = supportsWebGL() ? "" : " Renderizado en modo compatible sin WebGL.";
  setStatus(`Variable ${payload.variable}, ${statusPeriodText(payload)}.${sampleText}${renderText}`);
}

async function exportData(format) {
  setStatus(`Exportando ${format.toUpperCase()}...`);
  const form = new FormData();
  form.append("session_id", state.sessionId);
  form.append("format", format);
  const response = await api("/api/export", { method: "POST", body: form });
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  const filename = match?.[1] || `Agender_QC.${format}`;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
  setStatus(`Exportación completada: ${filename}`);
}

el.yearSelect.addEventListener("change", async () => {
  state.year = Number(el.yearSelect.value);
  syncPeriodOptions();
  await loadSeries();
});

el.monthSelect.addEventListener("change", async () => {
  state.month = el.monthSelect.value === "all" ? "all" : Number(el.monthSelect.value);
  if (state.month === "all") state.day = "all";
  syncPeriodOptions();
  await loadSeries();
});

el.daySelect.addEventListener("change", async () => {
  state.day = el.daySelect.value === "all" ? "all" : Number(el.daySelect.value);
  await loadSeries();
});

el.resolutionSelect.addEventListener("change", async () => {
  state.resolution = el.resolutionSelect.value;
  if (state.resolution === "year") state.month = "all";
  if (state.resolution === "month" || state.resolution === "year") state.day = "all";
  syncPeriodOptions();
  await loadSeries();
});

el.coverageInput.addEventListener("change", async () => {
  const value = Math.max(1, Math.min(100, Number(el.coverageInput.value) || 80));
  state.minCoverage = value;
  el.coverageInput.value = value;
  await loadSeries();
});

el.plotModeInputs.forEach((input) => {
  input.addEventListener("change", async () => {
    state.plotMode = input.value;
    await loadSeries();
  });
});

el.themeModeInputs.forEach((input) => {
  input.addEventListener("change", () => setThemeMode(input.value));
});

window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (state.themeMode === "system") applyTheme();
});

el.variableTabs.addEventListener("scroll", () => {
  requestAnimationFrame(updateTabScroller);
});
el.tabScrollLeftBtn.addEventListener("click", () => scrollVariableTabs(-1));
el.tabScrollRightBtn.addEventListener("click", () => scrollVariableTabs(1));
window.addEventListener("resize", () => requestAnimationFrame(updateTabScroller));

el.exportCsvBtn.addEventListener("click", () => exportData("csv"));
el.exportParquetBtn.addEventListener("click", () => exportData("parquet"));

applyTheme();
setControlsEnabled(false);
setStats({ total: 0, records: 0, missing: 0, completeness: 0 });
renderVariableTabs([]);

async function initializeViewer() {
  await waitForApi();
  const station = launchParams.get("station");
  if (!station) return;
  document.body.classList.add("embedded-viewer");
  try {
    await openStation(station, launchParams.get("source") === "quality" ? "quality" : "raw");
  } catch (error) {
    state.loading = false;
    failLoadProgress(`Error: ${error.message}`);
  }
}

initializeViewer();

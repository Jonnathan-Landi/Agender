(function () {
  const CONFIG_KEY = "agender.climatology.station-configuration";
  let initialized = false;
  let areas = [];
  let currentReport = null;
  const MONTHS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

  function init() {
    if (initialized) return;
    const dialog = document.querySelector("#climatology-settings-dialog");
    if (!dialog) return;
    initialized = true;

    document.querySelector("#climatology-settings").addEventListener("click", openSettings);
    document.querySelector("#climatology-empty-settings").addEventListener("click", openSettings);
    document.querySelector("#climatology-settings-close").addEventListener("click", () => dialog.close());
    document.querySelector("#climatology-settings-cancel").addEventListener("click", () => dialog.close());
    document.querySelector("#climatology-settings-form").addEventListener("submit", saveConfiguration);
    document.querySelector("#climatology-run").addEventListener("click", runReport);
    document.querySelector("#climatology-print").addEventListener("click", openPrintDialog);
    document.querySelector("#climatology-print-close").addEventListener("click", closePrintDialog);
    document.querySelector("#climatology-print-cancel").addEventListener("click", closePrintDialog);
    document.querySelector("#climatology-print-form").addEventListener("submit", exportPdf);
    document.querySelector("#climatology-print-all").addEventListener("change", toggleAllPrintAreas);
    document.querySelector("#climatology-print-areas").addEventListener("change", syncPrintAll);
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });

    updateStatus();
    loadStations();
  }

  async function loadStations() {
    const body = document.querySelector("#climatology-settings-body");
    try {
      const response = await fetch("/api/climatology/stations", {
        headers: { Accept: "application/json" },
        cache: "no-store"
      });
      const payload = await readApiResponse(response, "No fue posible consultar las estaciones.");
      areas = Array.isArray(payload.areas) ? payload.areas : [];
      renderAreas(body);
    } catch (error) {
      console.error(error);
      body.innerHTML = `<p class="climatology-settings-error">${escapeHtml(error.message)}</p>`;
    }
  }

  function openSettings() {
    const dialog = document.querySelector("#climatology-settings-dialog");
    document.querySelector("#climatology-dialog-message").textContent = "";
    if (areas.length) applyConfiguration();
    dialog.showModal();
  }

  function renderAreas(body) {
    const now = new Date();
    body.innerHTML = `
      <section class="climatology-period-card">
        <div class="climatology-area-title">
          <strong>Periodo del reporte</strong>
          <small>Se aplicará a todos los territorios</small>
        </div>
        <label class="climatology-station-field"><span>Año</span><input id="climatology-year" type="number" min="2000" max="2100" value="${now.getFullYear()}"></label>
        <label class="climatology-station-field"><span>Mes</span><select id="climatology-month">${MONTHS.map((name, index) => `<option value="${index + 1}">${name}</option>`).join("")}</select></label>
      </section>
    ` + areas.map((area) => `
      <section class="climatology-area-card" data-climatology-area="${escapeHtml(area.id)}">
        <div class="climatology-area-title">
          <strong>${escapeHtml(area.label)}</strong>
          <small>${escapeHtml(area.catalogBasin === "Cuenca" ? "Estaciones del área urbana" : `Estaciones de ${area.catalogBasin}`)}</small>
        </div>
        ${stationSelect(area, "temperature", "Estación de temperatura", area.temperatureStations)}
        ${stationSelect(area, "rain", "Estación de lluvia", area.rainStations)}
      </section>
    `).join("");
    applyConfiguration();
  }

  function stationSelect(area, variable, label, stations) {
    const options = stations.map((station) => {
      const altitude = station.altitude === "" ? "" : ` · ${formatAltitude(station.altitude)} m`;
      return `<option value="${escapeHtml(station.code)}">${escapeHtml(station.code)} · ${escapeHtml(station.type)}${altitude}</option>`;
    }).join("");
    return `
      <label class="climatology-station-field">
        <span>${label}</span>
        <select name="${escapeHtml(`${area.id}.${variable}`)}" data-area="${escapeHtml(area.id)}" data-variable="${variable}">
          <option value="">Seleccionar estación</option>
          ${options}
        </select>
      </label>
    `;
  }

  function applyConfiguration() {
    const saved = window.NotasStorage.loadJson(CONFIG_KEY, {});
    const now = new Date();
    const year = document.querySelector("#climatology-year");
    const month = document.querySelector("#climatology-month");
    if (year) year.value = saved.year || now.getFullYear();
    if (month) month.value = saved.month || Math.max(1, now.getMonth());
    document.querySelectorAll("#climatology-settings-body select").forEach((select) => {
      if (!select.dataset.area) return;
      select.value = saved?.[select.dataset.area]?.[select.dataset.variable] || "";
    });
  }

  async function saveConfiguration(event) {
    event.preventDefault();
    const configuration = {
      year: Number(document.querySelector("#climatology-year").value),
      month: Number(document.querySelector("#climatology-month").value)
    };
    document.querySelectorAll("#climatology-settings-body select").forEach((select) => {
      configuration[select.dataset.area] ||= {};
      configuration[select.dataset.area][select.dataset.variable] = select.value;
    });
    const button = document.querySelector("#climatology-settings-save");
    const message = document.querySelector("#climatology-dialog-message");
    button.disabled = true;
    message.textContent = "Guardando…";
    try {
      await window.NotasStorage.saveJson(CONFIG_KEY, configuration, { notify: false });
      message.textContent = "Configuración guardada";
      updateStatus(configuration);
      window.setTimeout(() => document.querySelector("#climatology-settings-dialog").close(), 250);
    } finally {
      button.disabled = false;
    }
  }

  function updateStatus(configuration = window.NotasStorage.loadJson(CONFIG_KEY, {})) {
    const selected = Object.values(configuration || {}).reduce(
      (total, area) => total + [area?.temperature, area?.rain].filter(Boolean).length,
      0
    );
    document.querySelector("#climatology-status").textContent = selected
      ? `${selected} de 10 estaciones configuradas`
      : "Estaciones pendientes de configurar";
  }

  async function runReport() {
    const configuration = window.NotasStorage.loadJson(CONFIG_KEY, {});
    const now = new Date();
    const previousMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const reportYear = Number(configuration.year) || previousMonth.getFullYear();
    const reportMonth = Number(configuration.month) || previousMonth.getMonth() + 1;
    const selections = Object.fromEntries(areas.map((area) => [area.id, {
      temperature: configuration?.[area.id]?.temperature || "",
      rain: configuration?.[area.id]?.rain || ""
    }]));
    const button = document.querySelector("#climatology-run");
    const status = document.querySelector("#climatology-status");
    const workspace = document.querySelector("#climatology-workspace");
    button.disabled = true;
    status.textContent = "Procesando 10 reportes…";
    workspace.innerHTML = `<div class="climatology-run-loading"><span class="station-viewer-spinner" aria-hidden="true"></span><strong>Generando climatología mensual</strong><span>Procesando temperatura y lluvia de todos los territorios…</span></div>`;
    try {
      const response = await fetch("/api/climatology/monthly-report", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ year: reportYear, month: reportMonth, areas: selections })
      });
      const result = await readApiResponse(response, "No fue posible generar el reporte.");
      renderReport(result, workspace);
      status.textContent = `${MONTHS[result.month - 1]} ${result.year} · reporte generado`;
    } catch (error) {
      console.error(error);
      workspace.innerHTML = `<div class="climatology-run-error"><strong>No se pudo generar el reporte</strong><span>${escapeHtml(error.message)}</span></div>`;
      status.textContent = "Error durante la ejecución";
    } finally {
      button.disabled = false;
    }
  }

  function renderReport(result, workspace) {
    currentReport = result;
    const period = `${MONTHS[result.month - 1]} ${result.year}`;
    workspace.innerHTML = `<div class="climatology-document">${result.areas.map((area) =>
      originalReportSheet(area.label, "temperature", area.temperature, period)
      + originalReportSheet(area.label, "rain", area.rain, period)
    ).join("")}</div>`;
    workspace.querySelectorAll(".climate-original-frame").forEach((frame) => {
      frame.addEventListener("load", () => {
        const height = frame.contentDocument?.documentElement?.scrollHeight;
        if (height) frame.style.height = `${height}px`;
      });
    });
  }

  function openPrintDialog() {
    const status = document.querySelector("#climatology-status");
    if (!currentReport?.areas?.length) {
      status.textContent = "Primero ejecuta el reporte mensual";
      return;
    }
    const body = document.querySelector("#climatology-print-areas");
    body.innerHTML = currentReport.areas.map((area) => {
      const available = area.temperature?.url && area.rain?.url;
      return `<label class="climatology-print-option${available ? "" : " is-disabled"}">
        <input type="checkbox" value="${escapeHtml(area.id)}" ${available ? "checked" : "disabled"}>
        <span>${escapeHtml(area.label)}</span>
      </label>`;
    }).join("");
    document.querySelector("#climatology-print-message").textContent = "";
    syncPrintAll();
    document.querySelector("#climatology-print-dialog").showModal();
  }

  function closePrintDialog() {
    document.querySelector("#climatology-print-dialog").close();
  }

  function toggleAllPrintAreas(event) {
    document.querySelectorAll("#climatology-print-areas input:not(:disabled)").forEach((input) => {
      input.checked = event.target.checked;
    });
  }

  function syncPrintAll() {
    const inputs = [...document.querySelectorAll("#climatology-print-areas input:not(:disabled)")];
    const selected = inputs.filter((input) => input.checked).length;
    const all = document.querySelector("#climatology-print-all");
    all.checked = inputs.length > 0 && selected === inputs.length;
    all.indeterminate = selected > 0 && selected < inputs.length;
  }

  async function exportPdf(event) {
    event.preventDefault();
    const selected = new Set(
      [...document.querySelectorAll("#climatology-print-areas input:checked")].map((input) => input.value)
    );
    const message = document.querySelector("#climatology-print-message");
    if (!selected.size) {
      message.textContent = "Selecciona al menos un territorio.";
      return;
    }
    const pages = currentReport.areas.filter((area) => selected.has(area.id)).flatMap((area) => [
      { territory: area.label, kind: "temperature", station: area.temperature.station, period: `${MONTHS[currentReport.month - 1]} ${currentReport.year}`, url: area.temperature.url },
      { territory: area.label, kind: "rain", station: area.rain.station, period: `${MONTHS[currentReport.month - 1]} ${currentReport.year}`, url: area.rain.url }
    ]);
    const button = document.querySelector("#climatology-print-export");
    button.disabled = true;
    message.textContent = "Preparando PDF…";
    try {
      const response = await fetch("/api/climatology/export-pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          pages,
          suggestedFileName: `Seguimiento_clima_${currentReport.year}_${String(currentReport.month).padStart(2, "0")}`
        })
      });
      const result = await readApiResponse(response, "No fue posible exportar el PDF.");
      message.textContent = result.message;
      if (!result.canceled) window.setTimeout(closePrintDialog, 450);
    } catch (error) {
      console.error(error);
      message.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  function originalReportSheet(territory, kind, report, period) {
    const isTemperature = kind === "temperature";
    const title = isTemperature ? "SEGUIMIENTO TÉRMICO" : "SEGUIMIENTO DE PRECIPITACIONES";
    const reportLabel = isTemperature ? "REPORTE TÉRMICO" : "REPORTE DE PRECIPITACIONES";
    const station = String(report.station || "ESTACIÓN PENDIENTE").replaceAll("_", " ");
    const heading = `<header class="climate-original-band"><h2>${title} <span>|</span> ${escapeHtml(period.toUpperCase())}</h2><p>SEGUIMIENTO MENSUAL DEL CLIMA EN LA ${escapeHtml(territory.toUpperCase())} · ESTACIÓN DE REFERENCIA: ${escapeHtml(station)}</p></header>`;
    if (report.error) {
      return `<article class="climate-original-sheet">${heading}<div class="climate-report-error"><span class="font-icon" aria-hidden="true">&#xEA39;</span><div><strong>${escapeHtml(report.station || reportLabel)}</strong><p>${escapeHtml(report.error)}</p></div></div></article>`;
    }
    return `<article class="climate-original-sheet">${heading}<iframe class="climate-original-frame" src="${escapeHtml(report.url)}" title="${escapeHtml(`${title} · ${territory}`)}"></iframe></article>`;
  }

  function formatAltitude(value) {
    return new Intl.NumberFormat("es-EC", { maximumFractionDigits: 0 }).format(Number(value));
  }

  async function readApiResponse(response, fallbackMessage) {
    const content = await response.text();
    let payload;
    try {
      payload = content ? JSON.parse(content) : {};
    } catch {
      throw new Error(response.ok ? "El servidor devolvió una respuesta no válida." : fallbackMessage);
    }
    if (!response.ok) throw new Error(payload.detail || fallbackMessage);
    return payload;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
    })[character]);
  }

  window.NotasClimatology = { init };
})();

(function () {
  const CONFIG_KEY = "agender.climatology.station-configuration";
  let initialized = false;
  let areas = [];
  let flowBasins = [];
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
      flowBasins = Array.isArray(payload.flowBasins) ? payload.flowBasins : [];
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
          <small>Se aplicará a ambas hojas</small>
        </div>
        <label class="climatology-station-field"><span>Año</span><input id="climatology-year" type="number" min="2000" max="2100" value="${now.getFullYear()}"></label>
        <label class="climatology-station-field"><span>Mes</span><select id="climatology-month">${MONTHS.map((name, index) => `<option value="${index + 1}">${name}</option>`).join("")}</select></label>
        <label class="climatology-station-field"><span>Criterio n (%)</span><input id="climatology-n-percent" type="number" min="1" max="100" step="1" value="80"></label>
      </section>
    ` + areas.map((area) => `
      <section class="climatology-area-card" data-climatology-area="${escapeHtml(area.id)}">
        <div class="climatology-area-title">
          <strong>${escapeHtml(area.label)}</strong>
          <small>Todas las estaciones compatibles están disponibles</small>
        </div>
        ${stationSelect(area, "temperature", "Estación de temperatura", area.temperatureStations)}
        ${stationSelect(area, "rain", "Estación de lluvia", area.rainStations)}
      </section>
    `).join("") + `
      <section class="climatology-flow-settings">
        <div class="climatology-area-title">
          <strong>Hoja 3 · Seguimiento de Caudales</strong>
          <small>Configure lluvia y caudal para cada tarjeta</small>
        </div>
        <div class="climatology-flow-settings-grid">
          ${flowBasins.map((basin) => `
            <article class="climatology-flow-basin" data-climatology-flow="${escapeHtml(basin.id)}">
              <strong>${escapeHtml(basin.label)}</strong>
              ${stationSelect({ id: `flows.${basin.id}` }, "rain", "Estación de lluvia", basin.rainStations || [])}
              ${stationSelect({ id: `flows.${basin.id}` }, "flow", "Estación de caudal", basin.flowStations || [])}
            </article>
          `).join("")}
        </div>
      </section>`;
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
    const nPercent = document.querySelector("#climatology-n-percent");
    if (year) year.value = saved.year || now.getFullYear();
    if (month) month.value = saved.month || Math.max(1, now.getMonth());
    if (nPercent) nPercent.value = saved.nPercent || 80;
    document.querySelectorAll("#climatology-settings-body select").forEach((select) => {
      if (!select.dataset.area) return;
      const path = select.dataset.area.split(".");
      select.value = path.length === 2
        ? saved?.[path[0]]?.[path[1]]?.[select.dataset.variable] || ""
        : saved?.[path[0]]?.[select.dataset.variable] || "";
    });
  }

  async function saveConfiguration(event) {
    event.preventDefault();
    const configuration = {
      year: Number(document.querySelector("#climatology-year").value),
      month: Number(document.querySelector("#climatology-month").value),
      nPercent: Number(document.querySelector("#climatology-n-percent").value)
    };
    document.querySelectorAll("#climatology-settings-body select").forEach((select) => {
      if (!select.dataset.area) return;
      const path = select.dataset.area.split(".");
      configuration[path[0]] ||= {};
      if (path.length === 2) {
        configuration[path[0]][path[1]] ||= {};
        configuration[path[0]][path[1]][select.dataset.variable] = select.value;
      } else {
        configuration[path[0]][select.dataset.variable] = select.value;
      }
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
    const areaSelected = areas.reduce((total, area) => total + [configuration?.[area.id]?.temperature, configuration?.[area.id]?.rain].filter(Boolean).length, 0);
    const flowSelected = flowBasins.reduce((total, basin) => total + [configuration?.flows?.[basin.id]?.rain, configuration?.flows?.[basin.id]?.flow].filter(Boolean).length, 0);
    const selected = areaSelected + flowSelected;
    document.querySelector("#climatology-status").textContent = selected
      ? `${selected} de 12 estaciones configuradas`
      : "Estaciones pendientes de configurar";
  }

  async function runReport() {
    const configuration = window.NotasStorage.loadJson(CONFIG_KEY, {});
    const now = new Date();
    const previousMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const reportYear = Number(configuration.year) || previousMonth.getFullYear();
    const reportMonth = Number(configuration.month) || previousMonth.getMonth() + 1;
    const nPercent = Math.min(100, Math.max(1, Number(configuration.nPercent) || 80));
    const selections = Object.fromEntries(areas.map((area) => [area.id, {
      temperature: configuration?.[area.id]?.temperature || "",
      rain: configuration?.[area.id]?.rain || ""
    }]));
    const flowSelections = Object.fromEntries(flowBasins.map((basin) => [basin.id, {
      rain: configuration?.flows?.[basin.id]?.rain || "",
      flow: configuration?.flows?.[basin.id]?.flow || ""
    }]));
    const button = document.querySelector("#climatology-run");
    const status = document.querySelector("#climatology-status");
    const workspace = document.querySelector("#climatology-workspace");
    button.disabled = true;
    status.textContent = "Procesando 3 hojas…";
    workspace.innerHTML = `<div class="climatology-run-loading"><span class="station-viewer-spinner" aria-hidden="true"></span><strong>Generando climatología mensual</strong><span>Procesando las hojas de Zona Urbana y Páramo…</span></div>`;
    try {
      const response = await fetch("/api/climatology/monthly-report", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ year: reportYear, month: reportMonth, nPercent, areas: selections, flows: flowSelections })
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
      originalReportSheet(area, period)
    ).join("")}${originalReportSheet(result.flows, period)}</div>`;
    workspace.querySelectorAll(".climate-original-frame").forEach(initializeReportFrame);
  }

  function initializeReportFrame(frame) {
    let resizeObserver;

    const synchronizeHeight = async () => {
      const document = frame.contentDocument;
      if (!document?.documentElement || !document.body) return;

      try {
        await document.fonts?.ready;
        await Promise.all([...document.images].map((image) => {
          if (image.complete) return Promise.resolve();
          return new Promise((resolve) => {
            image.addEventListener("load", resolve, { once: true });
            image.addEventListener("error", resolve, { once: true });
          });
        }));
      } catch (_error) {
        // A failed decorative asset must not prevent the report from sizing.
      }

      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      const applyHeight = () => {
        const height = Math.ceil(Math.max(document.documentElement.scrollHeight, document.body.scrollHeight));
        if (height >= 600 && height <= 1400 && frame.style.height !== `${height}px`) {
          frame.style.height = `${height}px`;
        }
      };
      applyHeight();
      resizeObserver?.disconnect();
      resizeObserver = new ResizeObserver(applyHeight);
      resizeObserver.observe(document.documentElement);
      resizeObserver.observe(document.body);
    };

    frame.addEventListener("load", synchronizeHeight);
    if (frame.contentDocument?.readyState === "complete") synchronizeHeight();
  }

  function openPrintDialog() {
    const status = document.querySelector("#climatology-status");
    if (!currentReport?.areas?.length) {
      status.textContent = "Primero ejecuta el reporte mensual";
      return;
    }
    const body = document.querySelector("#climatology-print-areas");
    body.innerHTML = [...currentReport.areas, currentReport.flows].map((area) => {
      const available = area.id === "flows" ? area.url : area.report?.url;
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
    const pages = currentReport.areas.filter((area) => selected.has(area.id)).map((area) => ({
      territory: area.label,
      station: area.report.station,
      period: `${MONTHS[currentReport.month - 1]} ${currentReport.year}`,
      url: area.report.url
    }));
    if (selected.has("flows")) pages.push({
      territory: "Seguimiento de Caudales",
      station: "Cuatro cuencas",
      period: `${MONTHS[currentReport.month - 1]} ${currentReport.year}`,
      url: currentReport.flows.url
    });
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

  function originalReportSheet(area, period) {
    const isFlows = area.id === "flows";
    const report = isFlows ? area : area.report;
    const territory = area.label;
    const title = isFlows ? "SEGUIMIENTO DE CAUDALES" : "SEGUIMIENTO TÉRMICO Y DE PRECIPITACIONES";
    const reportLabel = "REPORTE CLIMATOLÓGICO";
    const station = String(report.station || "ESTACIÓN PENDIENTE").replaceAll("_", " ");
    const location = area.id === "paramo" ? "EN EL PÁRAMO" : "EN LA ZONA URBANA";
    const subtitle = isFlows
      ? "LLUVIA VS CAUDAL · YANUNCAY · TOMEBAMBA · TARQUI · MACHÁNGARA"
      : `SEGUIMIENTO MENSUAL DEL CLIMA ${location} · ESTACIÓN DE REFERENCIA: ${escapeHtml(station)}`;
    const heading = `<header class="climate-original-band"><div class="climate-original-heading"><h2>${title} <span>|</span> ${escapeHtml(period.toUpperCase())}</h2><p>${subtitle}</p></div><div class="climate-original-brand" aria-label="ETAPA"><strong>ETAPA</strong><span aria-hidden="true">❯❯</span></div></header>`;
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

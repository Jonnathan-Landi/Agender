import { createDailyHeader } from "./daily-flows.js";

const stations = ["Cebollar", "Sustag", "Tixán", "Culebrillas"];
const metrics = [["Turbidez", "NTU", "💧"], ["pH", "-", "⚗"], ["Conductividad específica", "µS/cm", "≋"], ["Temperatura del agua", "°C", "♨"], ["Hidrocarburos", "RFU", "💧"]];
const labels = {normal: "NORMAL", prealert: "PREALERTA", alert: "ALERTA", missing: "SIN DATOS"};

export function createManualQualityPage() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  return `<section class="report-page daily-flow-page manual-quality-page">${createDailyHeader(local)}
    <div class="manual-quality-content"><div class="manual-summary">
      <article><span class="manual-summary-icon">💧</span><div><h2>ESTACIONES MONITOREADAS</h2><strong data-summary="stations">0</strong><small>de 4 estaciones</small></div></article>
      <article><span class="manual-summary-icon">☷</span><div><h2>PARÁMETROS REPORTADOS</h2><strong data-summary="parameters">0</strong><small>de 5 principales</small></div></article>
      <article><span class="manual-summary-icon">✓</span><div><h2>ESTADO GENERAL</h2><strong data-summary="status" data-state="missing">SIN DATOS</strong><small>Según estados ingresados</small></div></article>
      <article><span class="manual-summary-icon">▤</span><div><h2>TIPO DE REPORTE</h2><b>Calidad del agua cruda</b><small>Valores de ingreso manual</small></div></article>
    </div><section class="manual-quality-panel"><h2>CALIDAD DEL AGUA CRUDA POR ESTACIÓN</h2>
      <table class="manual-quality-table"><thead><tr><th>Estación</th>${metrics.map(([name, unit, icon]) => `<th><span class="manual-metric-icon">${icon}</span><span>${name}<small>(${unit})</small></span></th>`).join("")}<th>Estado de la estación</th></tr></thead>
      <tbody>${stations.map((station, index) => `<tr><th scope="row">${station}</th>${metrics.map(([name, unit], metric) => `<td><span class="manual-value-dot" aria-hidden="true"></span><input type="number" step="any" data-manual-key="value-${index}-${metric}" data-metric="${metric}" aria-label="${station}: ${name} (${unit})" placeholder="N/D"></td>`).join("")}<td class="manual-station-state" data-state="missing"><span class="manual-state-dot" aria-hidden="true"></span><select data-manual-key="status-${index}" aria-label="Estado de ${station}">${Object.entries(labels).map(([value, label]) => `<option value="${value}" ${value === "missing" ? "selected" : ""}>${label}</option>`).join("")}</select></td></tr>`).join("")}</tbody></table>
    </section></div><div class="footer">ETAPA EP – Red Hidrometeorológica | Página 2 de 2</div></section>`;
}

export function refreshManualQuality() {
  const page = document.querySelector(".manual-quality-page");
  if (!page) return;
  let stationCount = 0;
  const parameters = new Set(), states = [];
  page.querySelectorAll("tbody tr").forEach(row => {
    let hasValues = false;
    row.querySelectorAll("input").forEach(input => {
      const present = input.value !== "" && Number.isFinite(input.valueAsNumber);
      input.closest("td").classList.toggle("has-value", present);
      if (present) { hasValues = true; parameters.add(input.dataset.metric); }
    });
    if (hasValues) stationCount++;
    const state = row.querySelector("select").value;
    row.querySelector(".manual-station-state").dataset.state = state;
    states.push(state);
  });
  const state = states.includes("alert") ? "alert" : states.includes("prealert") ? "prealert" : states.every(s => s === "normal") ? "normal" : "missing";
  page.querySelector('[data-summary="stations"]').textContent = stationCount;
  page.querySelector('[data-summary="parameters"]').textContent = parameters.size;
  page.querySelector('[data-summary="status"]').textContent = labels[state];
  page.querySelector('[data-summary="status"]').dataset.state = state;
}

export function initializeManualQuality() {
  const page = document.querySelector(".manual-quality-page");
  if (!page) return;
  page.addEventListener("input", refreshManualQuality);
  page.addEventListener("change", refreshManualQuality);
  document.addEventListener("wqreport:clearmanual", clearManualQuality);
  refreshManualQuality();
}

export function readManualQuality() {
  return Object.fromEntries([...document.querySelectorAll("[data-manual-key]")].map(el => [el.dataset.manualKey, el.value]));
}

export function restoreManualQuality(values = {}) {
  document.querySelectorAll("[data-manual-key]").forEach(el => {
    if (Object.hasOwn(values, el.dataset.manualKey)) el.value = values[el.dataset.manualKey];
  });
  refreshManualQuality();
}

export function clearManualQuality() {
  document.querySelectorAll("[data-manual-key]").forEach(el => { el.value = el.tagName === "SELECT" ? "missing" : ""; });
  refreshManualQuality();
}

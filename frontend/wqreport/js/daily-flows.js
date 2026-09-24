const names = ["Tomebamba", "Yanuncay", "Tarqui", "Machángara"];
const escape = value => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));

function categoryBadge(label, category) {
  return `<span class="daily-weather-category" data-category="${category}">${label}</span>`;
}

export function rainCategory(value) {
  if (!Number.isFinite(value) || value < 0) return categoryBadge("Sin datos", "missing");
  if (value < 0.1) return categoryBadge("Sin lluvia", "dry");
  if (value < 2) return categoryBadge("Lluvia no significativa", "trace");
  if (value < 5) return categoryBadge("Lluvia ligera", "light");
  if (value < 20) return categoryBadge("Lluvia moderada", "moderate");
  if (value < 35) return categoryBadge("Lluvia intensa", "heavy");
  return categoryBadge("Lluvia muy intensa", "extreme");
}

export function createDailyHeader(local) {
  return `<header class="daily-banner"><img src="../assets/report-logos/logo ETAPA EP_mejorado_v3.png" alt="Alcaldía de Cuenca · ETAPA EP"><div class="daily-banner-title"><h1>REPORTE DIARIO DE LA RED HIDROMETEOROLÓGICA</h1><p>SISTEMA DE MONITOREO AUTOMÁTICO – ETAPA EP</p></div><div class="date-card"><button type="button" class="calendar-button" aria-label="Seleccionar fecha y hora">📅</button><input type="datetime-local" class="report-date-input" value="${local}"><span class="report-date-text"></span></div></header>`;
}

export function createDailyFlowPage() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  const table = (title, unit, key) => `<section class="daily-table" data-weather="${key}"><h2>${title}</h2><table><thead><tr><th>Cuenca</th><th>${unit}</th><th>Categoría</th></tr></thead><tbody>${names.map(name => `<tr><th>${name}</th><td>—</td><td>${key === "temperature" ? categoryBadge("Normal", "normal") : "Cargando…"}</td></tr>`).join("")}</tbody></table></section>`;
  return `<section class="report-page daily-flow-page">
    ${createDailyHeader(local)}
    <div class="daily-grid">${names.map(name => `<article class="daily-card"><header><h2><span class="daily-water-icon">≋</span>${name}</h2><span class="daily-badge" data-state="missing">SIN DATOS</span><div class="daily-current"><span class="daily-current-icon" aria-hidden="true">≋</span><div><small>Caudal actual</small><strong class="daily-value">— m³/s</strong></div></div></header><div class="daily-chart">Cargando datos…</div></article>`).join("")}</div>
    <div class="daily-tables">${table("Lluvia acumulada", "Lluvia (mm)", "rain")}${table("Temperatura mínima", "Temperatura (°C)", "temperature")}</div>
    <div class="footer">ETAPA EP – Red Hidrometeorológica | Página 1 de 2</div>
  </section>`;
}

function chart(card, start, end) {
  const left = 68, top = 10, width = 722, height = 260;
  const from = new Date(start).getTime(), to = new Date(end).getTime();
  const valid = card.points.filter(p => Number.isFinite(p.value));
  if (!valid.length) return `<div class="daily-empty">${escape(card.error || "Sin datos en el período seleccionado")}</div>`;
  const maximum = Math.max(2.5, ...valid.map(p => p.value)) * 1.15;
  const x = time => left + (new Date(time).getTime() - from) / (to - from) * width;
  const y = value => top + height - value / maximum * height;
  const segments = [];
  let segment = [];
  for (const point of card.points) {
    if (!Number.isFinite(point.value)) {
      if (segment.length) segments.push(segment);
      segment = [];
    } else segment.push(point);
  }
  if (segment.length) segments.push(segment);
  const line = points => points.map((p, i) => `${i ? "L" : "M"}${x(p.time).toFixed(2)},${y(p.value).toFixed(2)}`).join(" ");
  const path = segments.map(line).join(" ");
  const area = segments.map(points => `${line(points)} L${x(points.at(-1).time)},${top + height} L${x(points[0].time)},${top + height}Z`).join(" ");
  const rows = Array.from({length: 5}, (_, i) => {
    const value = maximum * i / 4, yy = y(value);
    return `<path d="M${left},${yy}H${left + width}" stroke="#dfe7ed"/><text x="${left - 10}" y="${yy + 5}" text-anchor="end">${value.toFixed(1)}</text>`;
  }).join("");
  const ticks = Array.from({length: 13}, (_, i) => {
    const date = new Date(from + i * (to - from) / 12), xx = left + i * width / 12;
    const label = `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
    return `<path d="M${xx},${top}V${top + height}" stroke="#edf1f5"/><text x="${xx}" y="${top + height + 28}" text-anchor="middle">${label}</text>`;
  }).join("");
  const last = valid.at(-1);
  const dots = valid.map(p => `<circle cx="${x(p.time)}" cy="${y(p.value)}" r="2" fill="#175ba3"/>`).join("");
  const low = card.lowThreshold ?? 2, dry = card.dryThreshold ?? 1.2;
  const gradient = `flow-fill-${names.indexOf(card.label)}`;
  const thresholds = `<path d="M${left},${y(low)}H${left + width}" stroke="#e6a126" stroke-width="2.5" stroke-dasharray="8 5"/><path d="M${left},${y(dry)}H${left + width}" stroke="#d52228" stroke-width="2.5" stroke-dasharray="8 5"/>`;
  const legend = `<g font-size="20" fill="#174e87"><path d="M85,327h48" stroke="#175ba3" stroke-width="3"/><text x="140" y="333">Caudal horario (m³/s)</text><path d="M350,327h45" stroke="#e6a126" stroke-width="3" stroke-dasharray="8 5"/><text x="405" y="333">Q bajo = ${low.toFixed(1)} m³/s</text><path d="M585,327h45" stroke="#d52228" stroke-width="3" stroke-dasharray="8 5"/><text x="640" y="333">Q estiaje = ${dry.toFixed(1)} m³/s</text></g>`;
  return `<svg viewBox="0 0 860 345" role="img" aria-label="Caudal horario de ${escape(card.label)} en las últimas 24 horas"><defs><linearGradient id="${gradient}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#56b3d8" stop-opacity="0.3"/><stop offset="100%" stop-color="#56b3d8" stop-opacity="0.02"/></linearGradient></defs><g fill="#50627a" font-size="19">${rows}${ticks}<path d="M${left},${top}V${top + height}H${left + width}" fill="none" stroke="#b9c7d2" stroke-width="1.5"/><text transform="translate(19 140) rotate(-90)" text-anchor="middle">Caudal (m³/s)</text></g><path d="${area}" fill="url(#${gradient})"/>${thresholds}<path d="${path}" fill="none" stroke="#175ba3" stroke-width="3"/>${dots}<circle cx="${x(last.time)}" cy="${y(last.value)}" r="7" fill="#175ba3"/>${legend}</svg>`;

}

export function initializeDailyFlows() {
  const page = document.querySelector(".daily-flow-page");
  if (!page) return;
  const input = page.querySelector(".report-date-input");
  let request = 0;
  async function refresh() {
    const id = ++request;
    const cards = [...page.querySelectorAll(".daily-card")];
    page.querySelectorAll(".daily-table tbody tr").forEach(row => {
      row.cells[1].textContent = "—";
      row.cells[2].innerHTML = row.closest("[data-weather]").dataset.weather === "temperature" ? categoryBadge("Normal", "normal") : "Cargando…";
    });
    cards.forEach(card => {
      card.querySelector(".daily-value").textContent = "— m³/s";
      card.querySelector(".daily-badge").dataset.state = "missing";
      card.querySelector(".daily-badge").textContent = "SIN DATOS";
      card.querySelector(".daily-chart").textContent = "Cargando datos…";
    });
    try {
      if (!input.value) throw new Error("Seleccione una fecha y hora.");
      const response = await fetch(`/api/reports/caudales/daily?end=${encodeURIComponent(input.value)}`);
      const data = await response.json();
      if (id !== request) return;
      if (!response.ok) throw new Error(data.detail || "No se pudieron cargar los caudales.");
      data.cards.forEach((card, index) => {
        cards[index].querySelector(".daily-value").textContent = `${card.current == null ? "—" : card.current.toFixed(2)} m³/s`;
        const badge = cards[index].querySelector(".daily-badge");
        badge.dataset.state = card.status || "missing";
        badge.textContent = {normal: "NORMAL", prealert: "PREALERTA", alert: "ALERTA", missing: "SIN DATOS"}[card.status || "missing"];
        badge.title = card.error || "Estado del promedio horario seleccionado";
        cards[index].querySelector(".daily-chart").innerHTML = chart(card, data.start, data.end);
      });
      for (const key of ["rain", "temperature"]) {
        const rows = page.querySelectorAll(`[data-weather="${key}"] tbody tr`);
        data.weather.forEach((basin, index) => {
          const metric = basin[key];
          rows[index].cells[0].textContent = basin.label;
          rows[index].cells[1].textContent = metric.value == null ? "—" : metric.value.toFixed(1);
          rows[index].cells[2].innerHTML = key === "temperature" ? categoryBadge("Normal", "normal") : rainCategory(metric.value);
          rows[index].cells[1].title = metric.error || "";
        });
      }
    } catch (error) {
      if (id !== request) return;
      page.querySelectorAll(".daily-table tbody tr").forEach(row => { row.cells[2].innerHTML = row.closest("[data-weather]").dataset.weather === "temperature" ? categoryBadge("Normal", "normal") : categoryBadge("Sin datos", "missing"); });
      cards.forEach(card => { card.querySelector(".daily-chart").textContent = error.message || "Datos no disponibles"; });
    }
  }
  input.addEventListener("change", refresh);
  refresh();
}

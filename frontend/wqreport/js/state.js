import { culebrillasVisibleParameters, defaultParameterOrder, parameterUnits, stationThresholds } from "./data.js";
import { extractNumericValue, normalizeText } from "./utils.js";

const parameterDefaultUnits = new Map(Object.entries(parameterUnits));
const parameterKeyAliases = new Map([
  ["SAC455", "SAC 455"],
  ["SAC 455", "SAC 455"],
  ["PH", "PH"],
  ["MATERIA ORGANICA DISUELTA", "MATERIA ORGANICA DISUELTA"]
]);

function getNumericPrefix(value) {
  const text = String(value || "").trim();

  if (isUnitOnlyValue(text) || /^NaN\b/i.test(text)) {
    return "";
  }

  const match = text.match(/^[-+]?(?:\d+(?:[.,]\d+)?|[.,]\d+)\b/i);

  return match ? match[0] : "";
}

function getOperationalNumber(value, unit) {
  const text = String(value || "").trim();

  if (!text || isUnitOnlyValue(text)) {
    return "";
  }

  if (unit) {
    const escapedUnit = escapeRegExp(unit).replace(/\\\s/g, "\\s*");
    const unitPattern = new RegExp(`\\s*${escapedUnit}\\s*$`, "i");
    const withoutCanonicalUnit = text.replace(unitPattern, "").trim();
    const normalizedSlashUnit = unit === "1/m"
      ? withoutCanonicalUnit.replace(/\s*\/m\s*$/i, "").trim()
      : withoutCanonicalUnit;
    const numericValue = getNumericPrefix(normalizedSlashUnit);

    if (numericValue) return numericValue;
  }

  return getNumericPrefix(text);
}

function isUnitOnlyValue(value) {
  return /^1\s*\/m$/i.test(String(value || "").trim());
}

function normalizeUnitOnlyValue(value) {
  return String(value || "").trim().replace(/^1\s*\/m$/i, "1/m");
}

function formatValueWithUnit(value, unit) {
  const normalizedValue = String(value || "").trim();
  const normalizedUnit = normalizeUnitValue(unit);

  if (!normalizedUnit) return normalizedValue;

  return normalizedValue ? `${normalizedValue} ${normalizedUnit}` : normalizedUnit;
}

function normalizeUnitValue(value) {
  const text = String(value || "").trim();

  if (isUnitOnlyValue(text)) return normalizeUnitOnlyValue(text);

  return text;
}

function escapeRegExp(value) {
  return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function ensureParameterUnits(root = document) {
  let changed = false;

  root.querySelectorAll(".quality-table tbody tr").forEach(row => {
    const cell = row.querySelector(".parameter-value");

    if (!cell) return;

    const paramKey = getParameterRowKey(row);
    if (!parameterDefaultUnits.has(paramKey)) return;

    const defaultUnit = parameterDefaultUnits.get(paramKey) || "";
    const text = cell.textContent.trim();
    const numericValue = getOperationalNumber(text, defaultUnit);
    const nextValue = formatValueWithUnit(numericValue, defaultUnit);

    if (cell.textContent !== nextValue) {
      cell.textContent = nextValue;
      changed = true;
    }
  });

  return changed;
}

export function setGraphImage(img, src) {
  const card = img.closest(".graph-card");

  img.onerror = null;
  img.onload = null;

  img.classList.remove("is-missing");

  if (!src) {
    img.removeAttribute("src");
    img.classList.add("is-missing");
    card?.classList.remove("has-graph-image");
    return;
  }

  img.onerror = function() {
    this.onerror = null;
    this.removeAttribute("src");
    this.classList.add("is-missing");
    card?.classList.remove("has-graph-image");
  };

  img.onload = function() {
    this.classList.remove("is-missing");
    card?.classList.add("has-graph-image");
  };

  img.src = src;
}

export function updateParameterRowsForPage(page) {
  if (!page) return;

  const stationSelect = page.querySelector(".station-select");
  if (!stationSelect) return;

  const stationValue = stationSelect.value;
  const tableBody = page.querySelector(".quality-table tbody");
  const rows = Array.from(page.querySelectorAll(".quality-table tbody tr"));

  rows.forEach(row => {
    const paramKey = getParameterRowKey(row);

    if (stationValue === "CULEBRILLAS") {
      const shouldShow = culebrillasVisibleParameters.includes(paramKey);
      row.classList.toggle("is-hidden", !shouldShow);
    } else {
      row.classList.remove("is-hidden");
    }
  });

  if (tableBody) {
    sortParameterRows(tableBody, rows, stationValue === "CULEBRILLAS" ? culebrillasVisibleParameters : defaultParameterOrder);
  }
}

export function updateHydrocarbonNoteCardForPage(page) {
  if (!page) return;

  const stationSelect = page.querySelector(".station-select");
  const noteCard = page.querySelector(".hydrocarbon-note-card");

  if (!stationSelect || !noteCard) return;

  const stationValue = stationSelect.value;
  const shouldHide = stationValue === "CULEBRILLAS";

  noteCard.classList.toggle("is-hidden", shouldHide);
}

export function updateThresholdFlagsForPage(page) {
  if (!page) return;

  const stationSelect = page.querySelector(".station-select");
  if (!stationSelect) return;

  const stationValue = stationSelect.value;
  const thresholds = stationThresholds[stationValue];

  const rows = page.querySelectorAll(".quality-table tbody tr[data-param-key]");

  rows.forEach(row => {
    const paramKey = row.dataset.paramKey;
    const flag = row.querySelector(".threshold-flag");

    if (!flag) return;

    flag.classList.remove("is-alert");

    if (!thresholds || !(paramKey in thresholds)) return;

    const valueCell = row.querySelector(".parameter-value");
    const currentValue = extractNumericValue(valueCell ? valueCell.textContent : "");
    const limitValue = thresholds[paramKey];

    if (Number.isFinite(currentValue) && currentValue > limitValue) {
      flag.classList.add("is-alert");
    }
  });
}

export function updateGraphAveragesForPage(page) {
  if (!page) return;

  const graphCards = page.querySelectorAll(".graph-card[data-param-key]");

  graphCards.forEach(card => {
    const paramKey = card.dataset.paramKey;
    const avgBox = card.querySelector(".avg-box");
    const valueCell = page.querySelector(`.quality-table tbody tr[data-param-key="${paramKey}"] .parameter-value`);

    if (!avgBox || !valueCell) return;

    const value = valueCell.textContent.trim();
    const numericValue = extractNumericValue(value);
    avgBox.textContent = Number.isFinite(numericValue) ? `Promedio: ${value}` : "Promedio:";
  });
}

export function updateGraphCardsForStation(page) {
  if (!page) return;

  const stationSelect = page.querySelector(".station-select");
  if (!stationSelect) return;

  const shouldBlankNonTurbidityCards = stationSelect.value === "CULEBRILLAS";
  const graphCards = page.querySelectorAll(".graph-card[data-param-key]");

  graphCards.forEach(card => {
    const shouldBlank = shouldBlankNonTurbidityCards && card.dataset.paramKey !== "TURBIDEZ";
    card.classList.toggle("is-station-blank", shouldBlank);
  });
}

export function updateReportPageState(page) {
  updateParameterRowsForPage(page);
  updateHydrocarbonNoteCardForPage(page);
  updateThresholdFlagsForPage(page);
  updateGraphAveragesForPage(page);
  updateGraphCardsForStation(page);
}

export function updateAllReportState() {
  document.querySelectorAll(".report-page").forEach(updateReportPageState);
  updateReportFooters();
}

export function updateReportFooters() {
  const pages = Array.from(document.querySelectorAll(".report-page"));
  const footerPrefix = getFooterPrefix(pages[0]?.querySelector(".footer"));

  pages.forEach((page, index) => {
    const footer = page.querySelector(".footer");

    if (!footer) return;

    footer.textContent = `${footerPrefix} | Página ${index + 1} de ${pages.length}`;
  });
}

function getFooterPrefix(footer) {
  const text = footer?.textContent || "";
  const prefix = text
    .replace(/\s*\|\s*Página\s+\d+\s+de\s+\d+.*$/i, "")
    .trim();

  if (!prefix || !/(ETAPA|Departamento|Investigación|Monitoreo)/i.test(prefix)) {
    return "ETAPA EP – Departamento de Investigación y Monitoreo";
  }

  return prefix;
}

export function clearReportValuesAndGraphs() {
  document.querySelectorAll(".quality-table tbody tr").forEach(row => {
    const cell = row.querySelector(".parameter-value");

    if (!cell) return;

    const paramKey = getParameterRowKey(row);
    if (!parameterDefaultUnits.has(paramKey)) return;

    const defaultUnit = parameterDefaultUnits.get(paramKey) || "";
    cell.textContent = formatValueWithUnit("", defaultUnit);
  });

  ensureParameterUnits();

  document.querySelectorAll(".graph-image").forEach(img => {
    setGraphImage(img, "");
    img.classList.remove("is-selected");
  });

  updateAllReportState();
}

function getParameterRowKey(row) {
  const rawKey = row?.dataset?.paramKey || getParameterNameText(row);
  const normalizedKey = normalizeText(rawKey).replace(/\s+/g, " ");
  const compactKey = normalizedKey.replace(/\s+/g, "");

  return parameterKeyAliases.get(normalizedKey) || parameterKeyAliases.get(compactKey) || normalizedKey;
}

function getParameterNameText(row) {
  const nameCell = row?.querySelector?.(".parameter-name");

  if (!nameCell) return "";

  const clone = nameCell.cloneNode(true);
  clone.querySelectorAll(".remove-parameter-row-button").forEach(button => button.remove());

  return clone.textContent || "";
}

function sortParameterRows(tableBody, rows, parameterOrder) {
  const orderedRows = [];
  const remainingRows = [...rows];

  parameterOrder.forEach(paramKey => {
    const rowIndex = remainingRows.findIndex(row => getParameterRowKey(row) === paramKey);

    if (rowIndex < 0) return;

    orderedRows.push(remainingRows.splice(rowIndex, 1)[0]);
  });

  [...orderedRows, ...remainingRows].forEach(row => tableBody.appendChild(row));
}

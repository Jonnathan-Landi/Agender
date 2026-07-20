import { isEditInheritanceEnabled, isEditModeEnabled, applyEditMode } from "./edit-mode.js";
import { ensureParameterUnits, updateGraphAveragesForPage, updateThresholdFlagsForPage } from "./state.js";
import { defaultParameterOrder, parameters } from "./data.js";
import { normalizeText } from "./utils.js";

const customRowAttribute = "data-custom-parameter-row";
const minObservationGap = 28;
const parameterKeyAliases = new Map([
  ["SAC455", "SAC 455"],
  ["SAC 455", "SAC 455"]
]);

export function initializeDynamicParameterRows() {
  ensureAllParameterRowControls();

  document.addEventListener("mousedown", event => {
    if (event.target.closest(".remove-parameter-row-button")) {
      event.preventDefault();
    }
  }, true);

  document.addEventListener("click", event => {
    const removeButton = event.target.closest(".remove-parameter-row-button");

    if (removeButton) {
      event.preventDefault();

      if (!isEditModeEnabled() || removeButton.disabled) {
        return;
      }

      removeParameterRow(removeButton.closest("tr"));
      refreshAddParameterRowButtons();
      return;
    }

    const button = event.target.closest(".add-parameter-row-button");

    if (!button) return;

    event.preventDefault();

    if (!isEditModeEnabled() || button.disabled) {
      return;
    }

    const page = button.closest(".report-page");

    if (!page || !canUseAddRowButton(page)) {
      refreshAddParameterRowButtons();
      return;
    }

    const row = addCustomParameterRow(page);

    if (isFirstReportPage(page) && isEditInheritanceEnabled()) {
      getReportPages().slice(1).forEach(targetPage => {
        if (canAddParameterRow(targetPage)) {
          addCustomParameterRow(targetPage);
        }
      });
    }

    refreshAddParameterRowButtons();
    row?.querySelector(".parameter-name")?.focus();
  });

  window.addEventListener("resize", refreshAddParameterRowButtons);
  document.addEventListener("wqreport:editmodechange", refreshParameterRowControls);
  document.addEventListener("wqreport:editinheritancechange", refreshParameterRowControls);
}

export function addCustomParameterRow(page, rowData = {}) {
  const tableBody = page?.querySelector(".quality-table tbody");

  if (!tableBody) return null;

  if (!rowData.rowKey) {
    rowData.rowKey = createCustomParameterRowKey(page);
  }

  const row = createCustomParameterRowElement(rowData);
  tableBody.appendChild(row);
  ensureParameterRowControls(row);
  applyEditMode();
  ensureParameterUnits(page);
  updateThresholdFlagsForPage(page);
  updateGraphAveragesForPage(page);

  return row;
}

export function serializeCustomParameterRows() {
  return getReportPages().map(page => {
    return getCustomParameterRows(page).map(row => {
      const nameCell = row.querySelector(".parameter-name");
      const valueCell = row.querySelector(".parameter-value");

      return {
        nameHtml: getEditableCellHtmlWithoutRowControls(nameCell),
        nameStyle: nameCell?.getAttribute("style") || "",
        valueHtml: getEditableCellHtmlWithoutRowControls(valueCell),
        valueStyle: valueCell?.getAttribute("style") || "",
        rowKey: row.dataset.customRowKey || ""
      };
    });
  });
}

export function serializeParameterRows() {
  return getReportPages().map(page => {
    return getParameterRows(page).map(row => {
      const nameCell = row.querySelector(".parameter-name");
      const valueCell = row.querySelector(".parameter-value");

      return {
        paramKey: row.dataset.paramKey || "",
        custom: isCustomParameterRow(row),
        rowKey: row.dataset.customRowKey || "",
        nameHtml: getEditableCellHtmlWithoutRowControls(nameCell),
        nameStyle: nameCell?.getAttribute("style") || "",
        valueHtml: getEditableCellHtmlWithoutRowControls(valueCell),
        valueStyle: valueCell?.getAttribute("style") || ""
      };
    });
  });
}

export function restoreCustomParameterRows(customRowsByPage) {
  if (!Array.isArray(customRowsByPage)) {
    return;
  }

  getReportPages().forEach((page, pageIndex) => {
    getCustomParameterRows(page).forEach(row => row.remove());

    const rows = Array.isArray(customRowsByPage[pageIndex]) ? customRowsByPage[pageIndex] : [];
    rows.forEach(rowData => addCustomParameterRow(page, rowData));
  });

  refreshAddParameterRowButtons();
}

export function restoreParameterRows(rowsByPage) {
  if (!Array.isArray(rowsByPage)) {
    return false;
  }

  getReportPages().forEach((page, pageIndex) => {
    const tableBody = page.querySelector(".quality-table tbody");
    const hasSavedRowsForPage = Array.isArray(rowsByPage[pageIndex]);
    const rows = hasSavedRowsForPage ? rowsByPage[pageIndex] : [];

    if (!tableBody || !hasSavedRowsForPage) return;

    tableBody.replaceChildren(...getMigratedParameterRows(rows).map(rowData => createParameterRowElement(rowData)));
  });

  refreshParameterRowControls();
  return true;
}

export function isCustomParameterRow(row) {
  return row?.hasAttribute?.(customRowAttribute);
}

function removeParameterRow(row) {
  if (!row || !row.closest(".quality-table tbody")) return;

  const page = row.closest(".report-page");
  const rowIndex = getParameterRows(page).indexOf(row);

  if (rowIndex < 0) return;

  row.remove();
  updatePageAfterRowRemoval(page);

  if (isFirstReportPage(page) && isEditInheritanceEnabled()) {
    getReportPages().slice(1).forEach(targetPage => {
      const targetRow = getParameterRows(targetPage)[rowIndex];

      if (!targetRow) return;

      targetRow.remove();
      updatePageAfterRowRemoval(targetPage);
    });
  }
}

export function refreshAddParameterRowButtons() {
  ensureAllParameterRowControls();

  document.querySelectorAll(".add-parameter-row-button").forEach(button => {
    const page = button.closest(".report-page");
    const canAdd = Boolean(page && canUseAddRowButton(page));

    button.disabled = !canAdd;
    button.title = isEditInheritanceEnabled() && page && !isFirstReportPage(page)
      ? "Con herencia activa, agrega filas desde la pagina 1"
      : canAdd
      ? "Agregar fila"
      : "No hay mas espacio para agregar filas en esta pagina";
  });

  document.querySelectorAll(".remove-parameter-row-button").forEach(button => {
    const row = button.closest("tr");
    const page = row?.closest(".report-page");
    const isBlockedByInheritance = Boolean(page && isEditInheritanceEnabled() && !isFirstReportPage(page));
    const canRemove = Boolean(isEditModeEnabled() && row && !isBlockedByInheritance);

    button.disabled = !canRemove;
    button.title = isBlockedByInheritance
      ? "Con herencia activa, elimina filas desde la pagina 1"
      : "Eliminar fila";
  });
}

export function refreshParameterRowControls() {
  ensureAllParameterRowControls();
  refreshAddParameterRowButtons();
}

function canUseAddRowButton(page) {
  if (!isEditModeEnabled()) return false;
  if (isEditInheritanceEnabled() && !isFirstReportPage(page)) return false;
  if (isEditInheritanceEnabled() && isFirstReportPage(page)) {
    return getReportPages().every(canAddParameterRow);
  }

  return canAddParameterRow(page);
}

function createCustomParameterRowElement(rowData = {}) {
  return createParameterRowElement({
    ...rowData,
    custom: true
  });
}

function createParameterRowElement(rowData = {}) {
  const row = document.createElement("tr");
  const paramKey = rowData.paramKey || "";
  const isCustom = rowData.custom || !paramKey;

  if (paramKey) {
    row.dataset.paramKey = paramKey;
  }

  if (isCustom) {
    row.setAttribute(customRowAttribute, "true");
    row.dataset.customRowKey = rowData.rowKey || createCustomParameterRowKey();
  }

  const nameCell = document.createElement("td");
  nameCell.className = "parameter-name editable-text-target";
  nameCell.dataset.editKey = isCustom
    ? `custom-parameter-name:${row.dataset.customRowKey}`
    : `parameter-name:${paramKey}`;
  nameCell.setAttribute("contenteditable", "true");
  nameCell.setAttribute("spellcheck", "false");
  nameCell.innerHTML = rowData.nameHtml ?? "Nuevo parametro";

  if (rowData.nameStyle) {
    nameCell.setAttribute("style", rowData.nameStyle);
  }

  const valueCell = document.createElement("td");
  valueCell.className = "parameter-value editable-text-target";
  valueCell.dataset.editKey = isCustom
    ? `custom-parameter-value:${row.dataset.customRowKey}`
    : `parameter-value:${paramKey}`;
  valueCell.setAttribute("contenteditable", "true");
  valueCell.setAttribute("spellcheck", "false");
  valueCell.innerHTML = rowData.valueHtml ?? "";

  if (rowData.valueStyle) {
    valueCell.setAttribute("style", rowData.valueStyle);
  }

  row.append(nameCell, valueCell);
  ensureParameterRowControls(row);
  return row;
}

function getMigratedParameterRows(rows) {
  const savedRowsByKey = getSavedOfficialRowsByKey(rows);
  const canonicalRows = parameters.map(([name, value]) => {
    const defaultRow = createDefaultParameterRowData(name, value);
    const savedRow = savedRowsByKey.get(defaultRow.paramKey);

    if (!savedRow) {
      return defaultRow;
    }

    return {
      ...defaultRow,
      valueHtml: savedRow.valueHtml ?? defaultRow.valueHtml,
      valueStyle: savedRow.valueStyle || ""
    };
  });
  const customRows = Array.isArray(rows)
    ? rows.filter(rowData => rowData.custom && !defaultParameterOrder.includes(normalizeParameterRowKey(rowData)))
    : [];

  return [...canonicalRows, ...customRows];
}

function getSavedOfficialRowsByKey(rows) {
  const savedRowsByKey = new Map();

  if (!Array.isArray(rows)) {
    return savedRowsByKey;
  }

  rows.forEach(rowData => {
    const paramKey = normalizeParameterRowKey(rowData);

    if (!defaultParameterOrder.includes(paramKey) || savedRowsByKey.has(paramKey)) {
      return;
    }

    savedRowsByKey.set(paramKey, rowData);
  });

  return savedRowsByKey;
}

function createDefaultParameterRowData(name, value) {
  const paramKey = normalizeText(name);
  const needsFlag = paramKey === "TURBIDEZ" || paramKey === "COLOR";
  const nameHtml = needsFlag
    ? `<span class="param-label">${name}<span class="threshold-flag" title="Valor sobre umbral">⚑</span></span>`
    : name;

  return {
    paramKey,
    custom: false,
    nameHtml,
    valueHtml: value
  };
}

function normalizeParameterRowKey(rowData = {}) {
  if (rowData.paramKey) {
    return canonicalParameterKey(rowData.paramKey);
  }

  return canonicalParameterKey(stripHtml(rowData.nameHtml || ""));
}

function canonicalParameterKey(value) {
  const normalizedKey = normalizeText(value).replace(/\s+/g, " ");
  const compactKey = normalizedKey.replace(/\s+/g, "");

  return parameterKeyAliases.get(normalizedKey) || parameterKeyAliases.get(compactKey) || normalizedKey;
}

function stripHtml(html) {
  const template = document.createElement("template");
  template.innerHTML = html || "";
  template.content.querySelectorAll(".remove-parameter-row-button").forEach(button => button.remove());

  return template.content.textContent || "";
}

function getEditableCellHtmlWithoutRowControls(cell) {
  if (!cell) return "";

  const clone = cell.cloneNode(true);
  clone.querySelectorAll(".remove-parameter-row-button").forEach(button => button.remove());

  return clone.innerHTML.trim();
}

function createRemoveParameterRowButton() {
  const button = document.createElement("button");
  button.className = "remove-parameter-row-button";
  button.type = "button";
  button.title = "Eliminar fila";
  button.setAttribute("aria-label", "Eliminar fila");
  button.setAttribute("contenteditable", "false");
  button.tabIndex = -1;
  button.innerHTML = '<span aria-hidden="true">×</span>';

  return button;
}

function ensureAllParameterRowControls() {
  document.querySelectorAll(".quality-table tbody tr").forEach(ensureParameterRowControls);
}

function ensureParameterRowControls(row) {
  const nameCell = row?.querySelector?.(".parameter-name");

  if (!nameCell || nameCell.querySelector(".remove-parameter-row-button")) return;

  nameCell.appendChild(createRemoveParameterRowButton());
}

function updatePageAfterRowRemoval(page) {
  updateThresholdFlagsForPage(page);
  updateGraphAveragesForPage(page);
}

function canAddParameterRow(page) {
  const table = page.querySelector(".quality-table");
  const noteCard = page.querySelector(".hydrocarbon-note-card:not(.is-hidden)");
  const observations = page.querySelector(".obs");
  const sampleRow = page.querySelector(".quality-table tbody tr:not(.is-hidden)");

  if (!table || !observations) {
    return false;
  }

  const rowHeight = Math.max(58, sampleRow?.getBoundingClientRect().height || 0);
  const tableBottom = table.getBoundingClientRect().bottom;
  const noteBottom = noteCard ? noteCard.getBoundingClientRect().bottom : tableBottom;
  const observationsTop = observations.getBoundingClientRect().top;
  const pageBottom = page.getBoundingClientRect().bottom;
  const observationsBottom = observations.getBoundingClientRect().bottom;
  const nextTableBottom = tableBottom + rowHeight;
  const nextNoteBottom = noteBottom + rowHeight;
  const nextObservationsBottom = observationsBottom + rowHeight;

  if (nextTableBottom >= observationsTop - minObservationGap) {
    return false;
  }

  if (nextNoteBottom >= observationsTop - minObservationGap && nextObservationsBottom >= pageBottom - minObservationGap) {
    return false;
  }

  return true;
}

function getReportPages() {
  return Array.from(document.querySelectorAll(".report-page"));
}

function isFirstReportPage(page) {
  return getReportPages()[0] === page;
}

function getCustomParameterRows(page) {
  return Array.from(page.querySelectorAll(`.quality-table tbody tr[${customRowAttribute}]`));
}

function getParameterRows(page) {
  return Array.from(page.querySelectorAll(".quality-table tbody tr"));
}

function createCustomParameterRowKey(page = null) {
  const pageRows = page ? getCustomParameterRows(page) : [];
  const maxIndex = pageRows.reduce((max, row) => {
    const match = String(row.dataset.customRowKey || "").match(/^custom-row-(\d+)$/);
    const value = match ? Number(match[1]) : 0;
    return Math.max(max, Number.isFinite(value) ? value : 0);
  }, 0);

  return `custom-row-${maxIndex + 1}`;
}

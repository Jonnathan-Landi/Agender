import { STORAGE_KEY } from "./data.js";
import { ensureParameterUnits, setGraphImage } from "./state.js";
import { restoreCustomParameterRows, restoreParameterRows, serializeCustomParameterRows, serializeParameterRows } from "./table-rows.js";

let standaloneConfig = null;

function getReportConfigElements() {
  return {
    editableElements: Array.from(document.querySelectorAll(".editable-text-target"))
      .filter(element => !element.closest(".ti-report-header") && !element.closest(".quality-table tbody")),
    tiHeaderEditableElements: Array.from(document.querySelectorAll(".ti-report-header .editable-text-target"))
      .filter(element => !element.closest(".quality-table tbody")),
    stationSelects: Array.from(document.querySelectorAll(".station-select")),
    tlpSelects: Array.from(document.querySelectorAll(".ti-header-tlp-select")),
    dateInputs: Array.from(document.querySelectorAll(".report-date-input")),
    graphImages: Array.from(document.querySelectorAll(".graph-image"))
  };
}

function serializeEditableElement(element) {
  return {
    key: element.dataset.editKey || "",
    html: element.innerHTML,
    style: element.getAttribute("style") || ""
  };
}

function applyEditableItemToElement(item, element) {
  if (!item || !element) return;
  if (!isValidEditableItemForElement(item, element)) return;

  element.innerHTML = item.html || "";

  if (item.style) {
    element.setAttribute("style", item.style);
  } else {
    element.removeAttribute("style");
  }
}

function isValidEditableItemForElement(item, element) {
  const key = item.key || element.dataset.editKey || "";
  const text = htmlToPlainText(item.html);

  if (key === "observations-title") {
    return /OBSERVACIONES/i.test(text);
  }

  if (key === "footer") {
    return /Página\s+\d+\s+de\s+\d+|ETAPA|Departamento|Investigación|Monitoreo/i.test(text);
  }

  return true;
}

function htmlToPlainText(html) {
  const template = document.createElement("template");
  template.innerHTML = html || "";

  return template.content.textContent || "";
}

function restoreEditableElementsByKey(items) {
  if (!Array.isArray(items)) {
    return false;
  }

  let restoredAny = false;

  items.forEach(item => {
    if (!item?.key) return;

    const element = document.querySelector(`.editable-text-target[data-edit-key="${cssEscape(item.key)}"]`);

    if (!element || element.closest(".quality-table tbody")) return;

    applyEditableItemToElement(item, element);
    restoredAny = true;
  });

  return restoredAny;
}

export async function saveConfig() {
  const { editableElements, tiHeaderEditableElements, stationSelects, tlpSelects, dateInputs, graphImages } = getReportConfigElements();
  const config = {
    editables: editableElements.map(serializeEditableElement),
    tiHeaderEditables: tiHeaderEditableElements.map(serializeEditableElement),
    stations: stationSelects.map(select => select.value),
    tlpProfiles: tlpSelects.map(select => select.value),
    dates: dateInputs.map(input => input.value),
    graphImages: graphImages.map(img => ({
      src: img.classList.contains("is-missing") ? "" : img.getAttribute("src") || ""
    })),
    parameterRows: serializeParameterRows(),
    customParameterRows: serializeCustomParameterRows()
  };

  try {
    const storage = window.parent?.NotasStorage;
    if (storage) {
      await storage.saveJson(STORAGE_KEY, config, { notify: false });
    } else {
      standaloneConfig = config;
    }
    return {
      ok: true,
      message: "Configuracion guardada."
    };
  } catch (error) {
    console.error("No se pudo guardar la configuracion:", error);
    return {
      ok: false,
      message: "No se pudo guardar la configuracion. Puede que las imagenes sean demasiado grandes."
    };
  }
}

export function loadConfig() {
  try {
    const storage = window.parent?.NotasStorage;
    const stagedConfig = window.parent?.NotasWaterQualitySession?.initialConfig;
    const config = stagedConfig || (storage
      ? storage.loadJson(STORAGE_KEY, null)
      : standaloneConfig
    );
    if (!config) return;
    const { editableElements, tiHeaderEditableElements, stationSelects, tlpSelects, dateInputs, graphImages } = getReportConfigElements();

    restoreEditableElementsByKey(config.editables);

    if (Array.isArray(config.stations)) {
      config.stations.forEach((value, index) => {
        if (stationSelects[index]) {
          stationSelects[index].value = value;
        }
      });
    }

    restoreEditableElementsByKey(config.tiHeaderEditables);

    if (Array.isArray(config.tlpProfiles)) {
      config.tlpProfiles.forEach((value, index) => {
        if (tlpSelects[index]) {
          tlpSelects[index].value = value;
        }
      });
    }

    if (Array.isArray(config.dates)) {
      config.dates.forEach((value, index) => {
        if (dateInputs[index]) {
          dateInputs[index].value = value;
        }
      });
    }

    if (Array.isArray(config.graphImages)) {
      config.graphImages.forEach((item, index) => {
        if (graphImages[index]) {
          setGraphImage(graphImages[index], item && item.src ? item.src : "");
        }
      });
    }

    if (!restoreParameterRows(config.parameterRows)) {
      restoreCustomParameterRows(config.customParameterRows);
    }
    ensureParameterUnits();
  } catch (error) {
    console.error("No se pudo cargar la configuracion guardada:", error);
  }
}

function cssEscape(value) {
  if (window.CSS && typeof window.CSS.escape === "function") {
    return window.CSS.escape(value);
  }

  return String(value).replace(/["\\]/g, "\\$&");
}

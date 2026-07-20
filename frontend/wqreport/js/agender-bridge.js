import { saveEditInheritance, saveEditMode, isEditInheritanceEnabled, isEditModeEnabled } from "./edit-mode.js";
import { getStoredPolicyProfile, savePolicyProfile } from "./policies.js";
import { clearReportValuesAndGraphs } from "./state.js";
import { saveConfig } from "./storage.js";

function serializeReports() {
  const reports = document.getElementById("reports");
  if (!reports) return "";
  const clone = reports.cloneNode(true);
  const originalControls = Array.from(reports.querySelectorAll("select, input, textarea"));
  const clonedControls = Array.from(clone.querySelectorAll("select, input, textarea"));

  originalControls.forEach((control, index) => {
    const clonedControl = clonedControls[index];
    if (!clonedControl) return;
    if (control.tagName === "SELECT") {
      Array.from(clonedControl.options).forEach(option => {
        option.toggleAttribute("selected", option.value === control.value);
      });
      clonedControl.value = control.value;
    } else if (control.tagName === "TEXTAREA") {
      clonedControl.textContent = control.value;
    } else if (control.type === "checkbox" || control.type === "radio") {
      clonedControl.toggleAttribute("checked", control.checked);
    } else {
      clonedControl.setAttribute("value", control.value);
    }
  });
  return clone.outerHTML;
}

function suggestedFileName() {
  const value = document.querySelector(".report-date-input")?.value || "";
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return "Reporte_CA";
  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  return `Reporte_CA_${day}${month}${date.getFullYear()}`;
}

function pageHeight() {
  return Math.max(1260, ...Array.from(document.querySelectorAll(".report-page"), page => (
    Math.ceil(Math.max(page.scrollHeight, page.offsetHeight, page.getBoundingClientRect().height))
  )));
}

function settings() {
  const editMode = isEditModeEnabled();
  return {
    policy: getStoredPolicyProfile(),
    editMode,
    editInheritance: editMode && isEditInheritanceEnabled(),
    editInheritanceEnabled: editMode
  };
}

function notify(type, detail = {}) {
  window.parent.postMessage({ source: "agender-wqreport", type, ...detail }, window.location.origin);
}

window.WQReportBridge = Object.freeze({
  async save() {
    const result = await saveConfig();
    notify("saved", { result });
    return result;
  },
  clear() {
    clearReportValuesAndGraphs();
    notify("changed");
  },
  getSettings: settings,
  setPolicy(value) {
    savePolicyProfile(value);
    notify("settings", { settings: settings() });
  },
  setEditMode(enabled) {
    saveEditMode(Boolean(enabled));
    notify("settings", { settings: settings() });
  },
  setEditInheritance(enabled) {
    saveEditInheritance(Boolean(enabled));
    notify("settings", { settings: settings() });
  },
  getExportPayload() {
    return {
      reportsHtml: serializeReports(),
      suggestedFileName: suggestedFileName(),
      pageHeight: pageHeight()
    };
  }
});

document.addEventListener("input", event => {
  if (event.target.closest?.("#reports")) notify("changed");
}, true);
document.addEventListener("change", event => {
  if (event.target.closest?.("#reports")) notify("changed");
}, true);
document.addEventListener("wqreport:reportchange", () => notify("changed"));
notify("ready", { settings: settings() });

import { renderReports } from "./render.js";

import {
  initializeCalendarControls,
  refreshCalendarDateDefaults,
  initializeStationControls,
  initializeTlpControls,
  initializeGraphImageControls,
  initializeTableValueControls
} from "./events.js";

import { initializeFormatMenu } from "./format-menu.js";
import { applyEditMode } from "./edit-mode.js";
import { applyPolicyProfile } from "./policies.js";
import { initializeDynamicParameterRows, refreshAddParameterRowButtons } from "./table-rows.js";
import { loadConfig } from "./storage.js";
import { updateAllReportState } from "./state.js";

renderReports();

initializeCalendarControls();
initializeStationControls();
initializeTlpControls();
initializeTableValueControls();
initializeGraphImageControls();
initializeFormatMenu();
initializeDynamicParameterRows();

loadConfig();
refreshCalendarDateDefaults();
updateAllReportState();

applyPolicyProfile();
applyEditMode();
refreshAddParameterRowButtons();

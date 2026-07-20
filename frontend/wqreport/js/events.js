import { formatDateLong } from "./utils.js";
import { updatePolicyHeaders } from "./policies.js";
import { isEditModeEnabled } from "./edit-mode.js";
import {
  setGraphImage,
  ensureParameterUnits,
  updateGraphAveragesForPage,
  updateReportPageState,
  updateThresholdFlagsForPage
} from "./state.js";

let selectedGraphImage = null;
let graphImageContextMenu = null;
let activeCrop = null;
const graphImageHistory = [];
let calendarControls = [];
let primaryDateValue = "";
let activeCalendarPicker = null;
let activeCalendarControl = null;

const calendarMonthNames = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
];

const calendarWeekDays = ["Do", "Lu", "Ma", "Mi", "Ju", "Vi", "Sa"];

function parseDateInputValue(value) {
  if (!value) {
    return new Date();
  }

  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);

  if (!match) {
    const fallbackDate = new Date(value);
    return Number.isNaN(fallbackDate.getTime()) ? new Date() : fallbackDate;
  }

  return new Date(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
    Number(match[4]),
    Number(match[5])
  );
}

function formatDateInputValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");

  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function getPickerStateFromDate(date) {
  return {
    viewYear: date.getFullYear(),
    viewMonth: date.getMonth(),
    selectedDate: new Date(date.getFullYear(), date.getMonth(), date.getDate()),
    selectedHour: date.getHours(),
    selectedMinute: date.getMinutes()
  };
}

function getCalendarPicker() {
  if (activeCalendarPicker) {
    return activeCalendarPicker;
  }

  const picker = document.createElement("div");
  picker.className = "report-date-picker";
  picker.hidden = true;
  picker.innerHTML = `
    <div class="report-date-picker-header">
      <button class="report-date-picker-nav" type="button" data-calendar-action="previous" aria-label="Mes anterior">
        <svg viewBox="0 0 20 20" aria-hidden="true">
          <path d="M12.5 4.5 7 10l5.5 5.5"></path>
        </svg>
      </button>
      <div class="report-date-picker-month"></div>
      <button class="report-date-picker-nav" type="button" data-calendar-action="next" aria-label="Mes siguiente">
        <svg viewBox="0 0 20 20" aria-hidden="true">
          <path d="M7.5 4.5 13 10l-5.5 5.5"></path>
        </svg>
      </button>
    </div>

    <div class="report-date-picker-content">
      <div class="report-date-calendar">
        <div class="report-date-weekdays"></div>
        <div class="report-date-days"></div>
      </div>

      <div class="report-time-picker">
        <div class="report-time-column">
          <div class="report-time-label">Hora</div>
          <div class="report-time-list" data-time-list="hour"></div>
        </div>
        <div class="report-time-column">
          <div class="report-time-label">Min</div>
          <div class="report-time-list" data-time-list="minute"></div>
        </div>
      </div>
    </div>

    <div class="report-date-picker-footer">
      <button class="report-date-picker-secondary" type="button" data-calendar-action="today">Hoy</button>
      <button class="report-date-picker-secondary" type="button" data-calendar-action="cancel">Cancelar</button>
      <button class="report-date-picker-primary" type="button" data-calendar-action="accept">Aceptar</button>
    </div>
  `;

  document.body.appendChild(picker);
  picker.addEventListener("click", handleCalendarPickerClick);
  activeCalendarPicker = picker;
  return picker;
}

function renderCalendarPicker() {
  if (!activeCalendarPicker || !activeCalendarControl) {
    return;
  }

  const { state } = activeCalendarControl;
  const monthLabel = activeCalendarPicker.querySelector(".report-date-picker-month");
  const weekdays = activeCalendarPicker.querySelector(".report-date-weekdays");
  const days = activeCalendarPicker.querySelector(".report-date-days");
  const hourList = activeCalendarPicker.querySelector('[data-time-list="hour"]');
  const minuteList = activeCalendarPicker.querySelector('[data-time-list="minute"]');

  monthLabel.textContent = `${calendarMonthNames[state.viewMonth]} ${state.viewYear}`;
  weekdays.innerHTML = calendarWeekDays.map(day => `<span>${day}</span>`).join("");

  const firstDay = new Date(state.viewYear, state.viewMonth, 1);
  const startDate = new Date(state.viewYear, state.viewMonth, 1 - firstDay.getDay());
  const today = new Date();
  const selectedTime = state.selectedDate.getTime();
  const dayButtons = [];

  for (let index = 0; index < 42; index++) {
    const date = new Date(startDate);
    date.setDate(startDate.getDate() + index);

    const isOutsideMonth = date.getMonth() !== state.viewMonth;
    const isToday = date.toDateString() === today.toDateString();
    const isSelected = date.getTime() === selectedTime;

    dayButtons.push(`
      <button
        class="report-date-day${isOutsideMonth ? " is-muted" : ""}${isToday ? " is-today" : ""}${isSelected ? " is-selected" : ""}"
        type="button"
        data-calendar-day="${formatDateInputValue(date).slice(0, 10)}"
      >${date.getDate()}</button>
    `);
  }

  days.innerHTML = dayButtons.join("");

  hourList.innerHTML = Array.from({ length: 24 }, (_, hour) => `
    <button class="report-time-option${hour === state.selectedHour ? " is-selected" : ""}" type="button" data-time-unit="hour" data-time-value="${hour}">
      ${String(hour).padStart(2, "0")}
    </button>
  `).join("");

  minuteList.innerHTML = Array.from({ length: 60 }, (_, minute) => `
    <button class="report-time-option${minute === state.selectedMinute ? " is-selected" : ""}" type="button" data-time-unit="minute" data-time-value="${minute}">
      ${String(minute).padStart(2, "0")}
    </button>
  `).join("");

  activeCalendarPicker.querySelectorAll(".report-time-option.is-selected").forEach(option => {
    option.scrollIntoView({ block: "nearest" });
  });
}

function positionCalendarPicker(button) {
  if (!activeCalendarPicker) {
    return;
  }

  const rect = button.getBoundingClientRect();
  const pickerRect = activeCalendarPicker.getBoundingClientRect();
  const padding = 12;
  const left = Math.min(
    Math.max(rect.left, padding),
    window.innerWidth - pickerRect.width - padding
  );
  const top = Math.min(
    rect.bottom + 10,
    window.innerHeight - pickerRect.height - padding
  );

  activeCalendarPicker.style.left = `${left}px`;
  activeCalendarPicker.style.top = `${Math.max(top, padding)}px`;
}

function openCalendarPicker(control) {
  const picker = getCalendarPicker();
  const selectedDate = parseDateInputValue(control.input.value);
  activeCalendarControl = {
    ...control,
    state: getPickerStateFromDate(selectedDate)
  };

  picker.hidden = false;
  renderCalendarPicker();
  positionCalendarPicker(control.button);
}

function closeCalendarPicker() {
  if (activeCalendarPicker) {
    activeCalendarPicker.hidden = true;
  }

  activeCalendarControl = null;
}

function commitCalendarPicker() {
  if (!activeCalendarControl) {
    return;
  }

  const { input, state } = activeCalendarControl;
  const selectedDate = new Date(
    state.selectedDate.getFullYear(),
    state.selectedDate.getMonth(),
    state.selectedDate.getDate(),
    state.selectedHour,
    state.selectedMinute
  );

  input.value = formatDateInputValue(selectedDate);
  input.dispatchEvent(new Event("change", { bubbles: true }));
  closeCalendarPicker();
}

function handleCalendarPickerClick(event) {
  const actionButton = event.target.closest("[data-calendar-action]");
  const dayButton = event.target.closest("[data-calendar-day]");
  const timeButton = event.target.closest("[data-time-unit]");

  if (!activeCalendarControl) {
    return;
  }

  const { state } = activeCalendarControl;

  if (actionButton) {
    const action = actionButton.dataset.calendarAction;

    if (action === "previous") {
      state.viewMonth -= 1;
      if (state.viewMonth < 0) {
        state.viewMonth = 11;
        state.viewYear -= 1;
      }
      renderCalendarPicker();
      return;
    }

    if (action === "next") {
      state.viewMonth += 1;
      if (state.viewMonth > 11) {
        state.viewMonth = 0;
        state.viewYear += 1;
      }
      renderCalendarPicker();
      return;
    }

    if (action === "today") {
      const today = new Date();
      state.viewYear = today.getFullYear();
      state.viewMonth = today.getMonth();
      state.selectedDate = new Date(today.getFullYear(), today.getMonth(), today.getDate());
      renderCalendarPicker();
      return;
    }

    if (action === "cancel") {
      closeCalendarPicker();
      return;
    }

    if (action === "accept") {
      commitCalendarPicker();
    }

    return;
  }

  if (dayButton) {
    const [year, month, day] = dayButton.dataset.calendarDay.split("-").map(Number);
    state.selectedDate = new Date(year, month - 1, day);
    state.viewYear = year;
    state.viewMonth = month - 1;
    renderCalendarPicker();
    return;
  }

  if (timeButton) {
    const value = Number(timeButton.dataset.timeValue);

    if (timeButton.dataset.timeUnit === "hour") {
      state.selectedHour = value;
    } else {
      state.selectedMinute = value;
    }

    renderCalendarPicker();
  }
}

function handleCalendarOutsideClick(event) {
  if (!activeCalendarPicker || activeCalendarPicker.hidden) {
    return;
  }

  if (activeCalendarPicker.contains(event.target) || event.target.closest(".calendar-button")) {
    return;
  }

  closeCalendarPicker();
}

function updateCalendarDateText(input) {
  const page = input.closest(".report-page");
  const reportDateText = page ? page.querySelector(".report-date-text") : null;

  if (reportDateText) {
    reportDateText.textContent = formatDateLong(input.value);
  }

  updatePolicyHeaders(page || document);
}

function setInheritedDate(input, value) {
  input.value = value;
  input.dataset.customDate = "false";
  updateCalendarDateText(input);
}

export function refreshCalendarDateDefaults() {
  if (!calendarControls.length) return;

  const firstInput = calendarControls[0].input;
  const firstValue = firstInput.value;

  calendarControls.forEach(({ input }, index) => {
    if (index === 0) {
      updateCalendarDateText(input);
      return;
    }

    if (!input.value || input.value === primaryDateValue) {
      setInheritedDate(input, firstValue);
    } else {
      input.dataset.customDate = input.value === firstValue ? "false" : "true";
      updateCalendarDateText(input);
    }
  });

  primaryDateValue = firstValue;
}

export function initializeCalendarControls() {
  const pages = document.querySelectorAll(".report-page");
  calendarControls = [];

  pages.forEach((page, index) => {
    const calendarButton = page.querySelector(".calendar-button");
    const reportDateInput = page.querySelector(".report-date-input");

    calendarButton.addEventListener("click", function() {
      openCalendarPicker({ button: calendarButton, input: reportDateInput, pageIndex: index });
    });

    reportDateInput.addEventListener("change", function() {
      if (index === 0) {
        const previousPrimaryDateValue = primaryDateValue;
        primaryDateValue = this.value;

        calendarControls.slice(1).forEach(({ input }) => {
          if (input.dataset.customDate === "true" && input.value !== previousPrimaryDateValue) {
            return;
          }

          setInheritedDate(input, this.value);
        });
      } else {
        this.dataset.customDate = this.value === calendarControls[0].input.value ? "false" : "true";
      }

      updateCalendarDateText(this);
    });

    calendarControls.push({ button: calendarButton, input: reportDateInput });
  });

  document.addEventListener("pointerdown", handleCalendarOutsideClick);
  window.addEventListener("resize", closeCalendarPicker);
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      closeCalendarPicker();
    }
  });

  primaryDateValue = calendarControls[0] ? calendarControls[0].input.value : "";
  refreshCalendarDateDefaults();
}

export function initializeStationControls() {
  const stationSelects = document.querySelectorAll(".station-select");

  stationSelects.forEach(select => {
    select.addEventListener("change", function() {
      updateReportPageState(this.closest(".report-page"));
    });
  });
}

export function initializeTlpControls() {
  const tlpSelects = Array.from(document.querySelectorAll(".ti-header-tlp-select"));
  const primaryTlpSelect = tlpSelects[0];

  if (!primaryTlpSelect) return;

  primaryTlpSelect.addEventListener("change", function() {
    tlpSelects.slice(1).forEach(select => {
      select.value = this.value;
    });
  });
}

export function initializeTableValueControls() {
  document.addEventListener("focusin", event => {
    const cell = event.target.closest?.(".parameter-value");

    if (!cell || isEditModeEnabled()) return;

    prepareOperationalValueCell(cell);
    selectOperationalValueNumber(cell);
  });

  document.addEventListener("beforeinput", event => {
    const cell = event.target.closest?.(".parameter-value");

    if (!cell || isEditModeEnabled()) return;

    handleOperationalValueBeforeInput(event, cell);
  }, true);

  document.addEventListener("keydown", event => {
    const cell = event.target.closest?.(".parameter-value");

    if (!cell || isEditModeEnabled() || event.key !== "Enter") return;

    event.preventDefault();
    focusNextParameterValueCell(cell);
  }, true);

  document.addEventListener("input", event => {
    const cell = event.target.closest?.(".parameter-value");

    if (!cell) return;

    const page = cell.closest(".report-page");
    updateThresholdFlagsForPage(page);
    updateGraphAveragesForPage(page);
  });

  document.addEventListener("blur", event => {
    const cell = event.target.closest?.(".parameter-value");

    if (!cell) return;

    const page = cell.closest(".report-page");
    normalizeParameterValueSpacing(cell);
    const unitsChanged = ensureParameterUnits(page);
    updateThresholdFlagsForPage(page);
    updateGraphAveragesForPage(page);

    if (unitsChanged) {
      document.dispatchEvent(new CustomEvent("wqreport:reportchange", {
        detail: { source: "parameter-units" }
      }));
    }
  }, true);
}

function normalizeParameterValueSpacing(cell) {
  const value = cell.textContent.trim();

  if (!value) return;

  if (isUnitOnlyValue(value)) {
    cell.textContent = normalizeUnitOnlyValue(value);
    return;
  }

  const formattedValue = value.replace(
    /^([-+]?(?:(?:\d+[.,]\d+)|(?:[.,]\d+)|\d+))\s*([^\d\s.,].*)$/i,
    "$1 $2"
  );

  if (formattedValue !== value) {
    cell.textContent = formattedValue;
  }
}

function handleOperationalValueBeforeInput(event, cell) {
  const inputType = event.inputType || "";

  if (inputType === "insertParagraph") {
    event.preventDefault();
    focusNextParameterValueCell(cell);
    return;
  }

  if (inputType.startsWith("insert")) {
    const text = inputType === "insertFromPaste"
      ? event.dataTransfer?.getData("text/plain") || event.clipboardData?.getData("text/plain") || event.data || ""
      : event.data || "";

    event.preventDefault();
    insertOperationalValueText(cell, text);
    return;
  }

  if (inputType.startsWith("delete")) {
    event.preventDefault();
    deleteOperationalValueText(cell, inputType);
    return;
  }

  event.preventDefault();
}

function prepareOperationalValueCell(cell) {
  const value = cell.textContent.trim();
  const number = getNumericPrefix(value);
  const unit = getUnitFromValue(value);

  cell.dataset.operationalUnit = unit;
  renderOperationalValueCell(cell, number, unit);
}

function insertOperationalValueText(cell, text) {
  const normalizedText = String(text || "").trim();

  if (!normalizedText || !/^[\d.,+-]+$/.test(normalizedText)) {
    showNumericValueDialog();
    return;
  }

  const { number, unit, start, end } = getOperationalValueSelection(cell);
  const nextNumber = `${number.slice(0, start)}${normalizedText}${number.slice(end)}`;

  if (!isValidPartialNumber(nextNumber)) {
    showNumericValueDialog();
    return;
  }

  renderOperationalValueCell(cell, nextNumber, unit);
  setOperationalValueCaret(cell, start + normalizedText.length);
  notifyParameterValueChanged(cell);
}

function deleteOperationalValueText(cell, inputType) {
  const { number, unit, start, end } = getOperationalValueSelection(cell);
  let nextStart = start;
  let nextEnd = end;

  if (start === end) {
    if (inputType === "deleteContentBackward") {
      nextStart = Math.max(0, start - 1);
    } else {
      nextEnd = Math.min(number.length, end + 1);
    }
  }

  const nextNumber = `${number.slice(0, nextStart)}${number.slice(nextEnd)}`;
  renderOperationalValueCell(cell, nextNumber, unit);
  setOperationalValueCaret(cell, nextStart);
  notifyParameterValueChanged(cell);
}

function renderOperationalValueCell(cell, number, unit = cell.dataset.operationalUnit || "") {
  const normalizedNumber = String(number || "");
  const normalizedUnit = normalizeUnitValue(unit);

  cell.dataset.operationalUnit = normalizedUnit;
  cell.textContent = normalizedUnit
    ? `${normalizedNumber}${normalizedNumber ? " " : ""}${normalizedUnit}`
    : normalizedNumber;
}

function getOperationalValueSelection(cell) {
  const number = getNumericPrefix(cell.textContent);
  const unit = cell.dataset.operationalUnit || getUnitFromValue(cell.textContent);
  const selection = window.getSelection();
  let start = number.length;
  let end = number.length;

  if (selection && selection.rangeCount && cell.contains(selection.anchorNode) && cell.contains(selection.focusNode)) {
    start = getTextOffsetWithinCell(cell, selection.anchorNode, selection.anchorOffset);
    end = getTextOffsetWithinCell(cell, selection.focusNode, selection.focusOffset);

    if (start > end) {
      [start, end] = [end, start];
    }
  }

  return {
    number,
    unit,
    start: Math.max(0, Math.min(start, number.length)),
    end: Math.max(0, Math.min(end, number.length))
  };
}

function getTextOffsetWithinCell(cell, node, offset) {
  const range = document.createRange();
  range.selectNodeContents(cell);

  try {
    range.setEnd(node, offset);
  } catch {
    return cell.textContent.length;
  }

  return range.toString().length;
}

function selectOperationalValueNumber(cell) {
  const number = getNumericPrefix(cell.textContent);
  setOperationalValueSelection(cell, 0, number.length);
}

function setOperationalValueCaret(cell, offset) {
  setOperationalValueSelection(cell, offset, offset);
}

function setOperationalValueSelection(cell, start, end) {
  const textNode = getOrCreateCellTextNode(cell);
  const safeStart = Math.max(0, Math.min(start, textNode.textContent.length));
  const safeEnd = Math.max(0, Math.min(end, textNode.textContent.length));
  const range = document.createRange();
  const selection = window.getSelection();

  range.setStart(textNode, safeStart);
  range.setEnd(textNode, safeEnd);
  selection.removeAllRanges();
  selection.addRange(range);
}

function getOrCreateCellTextNode(cell) {
  if (!cell.firstChild || cell.firstChild.nodeType !== Node.TEXT_NODE) {
    cell.textContent = cell.textContent;
  }

  return cell.firstChild;
}

function notifyParameterValueChanged(cell) {
  const page = cell.closest(".report-page");

  updateThresholdFlagsForPage(page);
  updateGraphAveragesForPage(page);
  cell.dispatchEvent(new Event("input", { bubbles: true }));
}

function focusNextParameterValueCell(cell) {
  const cells = Array.from(document.querySelectorAll(".parameter-value"));
  const currentIndex = cells.indexOf(cell);
  const nextCell = cells[currentIndex + 1] || cells[0];

  if (!nextCell || nextCell === cell) return;

  nextCell.focus();
  prepareOperationalValueCell(nextCell);
  selectOperationalValueNumber(nextCell);
}

function getUnitFromValue(value) {
  const text = String(value || "").trim();

  if (isUnitOnlyValue(text)) {
    return normalizeUnitOnlyValue(text);
  }

  return text
    .replace(/^(?:[-+]?(?:\d+(?:[.,]\d*)?|[.,]\d+)|[+-]?)\s*/i, "")
    .trim();
}

function getNumericPrefix(value) {
  const text = String(value || "").trim();

  if (isUnitOnlyValue(text)) {
    return "";
  }

  const match = text.match(/^[-+]?(?:(?:\d+(?:[.,]\d*)?)|(?:[.,]\d+))?/);

  return match ? match[0] : "";
}

function isUnitOnlyValue(value) {
  return /^1\s*\/m$/i.test(String(value || "").trim());
}

function normalizeUnitOnlyValue(value) {
  return String(value || "").trim().replace(/^1\s*\/m$/i, "1/m");
}

function normalizeUnitValue(value) {
  const text = String(value || "").trim();

  if (text === "/m" || isUnitOnlyValue(text)) {
    return "1/m";
  }

  return text;
}

function isValidPartialNumber(value) {
  return /^[-+]?(?:(?:\d+(?:[.,]\d*)?)|(?:[.,]\d+))?$/.test(value);
}

function showNumericValueDialog() {
  let backdrop = document.getElementById("numeric-value-dialog-backdrop");

  if (!backdrop) {
    backdrop = document.createElement("div");
    backdrop.id = "numeric-value-dialog-backdrop";
    backdrop.className = "app-modal-backdrop";
    backdrop.hidden = true;
    backdrop.innerHTML = `
      <section class="app-modal numeric-value-dialog" role="alertdialog" aria-modal="true" aria-labelledby="numeric-value-dialog-title">
        <header class="app-modal-header">
          <h2 id="numeric-value-dialog-title">Valor no valido</h2>
          <button class="app-modal-close-button" type="button" aria-label="Cerrar">×</button>
        </header>
        <div class="numeric-value-dialog-body">
          Solo se aceptan valores numericos en esta celda.
        </div>
        <footer class="numeric-value-dialog-actions">
          <button class="winui-button winui-button-primary" type="button">Aceptar</button>
        </footer>
      </section>
    `;
    document.body.appendChild(backdrop);

    backdrop.addEventListener("click", event => {
      if (event.target === backdrop || event.target.closest("button")) {
        backdrop.hidden = true;
      }
    });
  }

  backdrop.hidden = false;
  backdrop.querySelector(".winui-button-primary")?.focus();
}

function getImageFileFromDataTransfer(dataTransfer) {
  if (!dataTransfer) return null;

  const files = Array.from(dataTransfer.files || []);
  const directFile = files.find(file => file.type.startsWith("image/"));

  if (directFile) return directFile;

  const items = Array.from(dataTransfer.items || []);
  const imageItem = items.find(item => item.kind === "file" && item.type.startsWith("image/"));

  return imageItem ? imageItem.getAsFile() : null;
}

function loadGraphImageFile(slot, file) {
  if (!slot || !file || !file.type.startsWith("image/")) return;

  const img = slot.querySelector(".graph-image");
  const card = slot.closest(".graph-card");

  if (!img || !card) return;

  const reader = new FileReader();

  reader.onload = function() {
    setGraphImageWithHistory(img, reader.result);
    card.classList.add("has-graph-image");
    selectGraphImage(img);
  };

  reader.onerror = function() {
    console.error("No se pudo cargar la imagen seleccionada.");
  };

  reader.readAsDataURL(file);
}

function getGraphImageSrc(img) {
  return img && !img.classList.contains("is-missing") ? img.getAttribute("src") || "" : "";
}

function pushGraphImageHistory(img) {
  graphImageHistory.push({
    img,
    src: getGraphImageSrc(img)
  });
}

function setGraphImageWithHistory(img, src) {
  if (!img) return;

  pushGraphImageHistory(img);
  setGraphImage(img, src);
}

function undoLastGraphImageChange() {
  const lastState = graphImageHistory.pop();

  if (!lastState || !lastState.img) return false;

  setGraphImage(lastState.img, lastState.src);

  if (lastState.src) {
    selectGraphImage(lastState.img);
  } else {
    clearSelectedGraphImage();
  }

  return true;
}

function isTextEditingElement(element) {
  return Boolean(
    element &&
    (element.isContentEditable ||
      element.tagName === "INPUT" ||
      element.tagName === "TEXTAREA" ||
      element.tagName === "SELECT")
  );
}

function getGraphCardFromImage(img) {
  return img ? img.closest(".graph-card") : null;
}

function hasLoadedGraphImage(img) {
  return Boolean(img && getGraphCardFromImage(img)?.classList.contains("has-graph-image"));
}

function selectGraphImage(img) {
  if (selectedGraphImage && selectedGraphImage !== img) {
    selectedGraphImage.classList.remove("is-selected");
  }

  selectedGraphImage = hasLoadedGraphImage(img) ? img : null;

  if (selectedGraphImage) {
    selectedGraphImage.classList.add("is-selected");
    selectedGraphImage.focus();
  }
}

function clearSelectedGraphImage() {
  if (!selectedGraphImage) return;

  selectedGraphImage.classList.remove("is-selected");
  selectedGraphImage = null;
}

function removeGraphImage(img) {
  if (!hasLoadedGraphImage(img)) return;

  setGraphImageWithHistory(img, "");
  clearSelectedGraphImage();

  const uploadZone = img.closest(".graph-image-slot")?.querySelector(".graph-image-upload-zone");
  uploadZone?.focus();
}

function hideGraphImageContextMenu() {
  if (graphImageContextMenu) {
    graphImageContextMenu.hidden = true;
  }
}

function createGraphImageContextMenu() {
  const menu = document.createElement("div");
  menu.className = "graph-image-context-menu";
  menu.hidden = true;
  menu.innerHTML = `
    <button type="button" data-graph-action="crop">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7.25 17.75a2.75 2.75 0 1 1-3.89-3.89 2.75 2.75 0 0 1 3.89 3.89Z"></path>
        <path d="M7.25 6.25a2.75 2.75 0 1 0-3.89 3.89 2.75 2.75 0 0 0 3.89-3.89Z"></path>
        <path d="M8.8 8.8 20 4"></path>
        <path d="M8.8 15.2 20 20"></path>
        <path d="M8.9 12h.01"></path>
      </svg>
      <span>Recortar</span>
    </button>
    <button type="button" data-graph-action="remove">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 7h14"></path>
        <path d="M9.5 7V5.75C9.5 4.78 10.28 4 11.25 4h3.5c.97 0 1.75.78 1.75 1.75V7"></path>
        <path d="M7 7.5 7.83 18c.08 1.12.84 2 1.75 2h6.84c.91 0 1.67-.88 1.75-2L19 7.5"></path>
        <path d="M10.75 11v5"></path>
        <path d="M14.25 11v5"></path>
      </svg>
      <span>Borrar</span>
    </button>
  `;

  menu.addEventListener("click", event => {
    const actionButton = event.target.closest("button[data-graph-action]");

    if (!actionButton) return;

    hideGraphImageContextMenu();

    if (actionButton.dataset.graphAction === "crop") {
      startGraphImageCrop(selectedGraphImage);
      return;
    }

    if (actionButton.dataset.graphAction === "remove") {
      removeGraphImage(selectedGraphImage);
    }
  });

  document.body.appendChild(menu);

  return menu;
}

function getImageBoxInSlot(img, slot) {
  return {
    left: img.offsetLeft,
    top: img.offsetTop,
    width: img.offsetWidth,
    height: img.offsetHeight
  };
}

function setCropBoxRect(box, rect) {
  box.style.left = `${rect.left}px`;
  box.style.top = `${rect.top}px`;
  box.style.width = `${rect.width}px`;
  box.style.height = `${rect.height}px`;
}

function getCropBoxRect(box) {
  return {
    left: parseFloat(box.style.left) || 0,
    top: parseFloat(box.style.top) || 0,
    width: parseFloat(box.style.width) || 0,
    height: parseFloat(box.style.height) || 0
  };
}

function clampCropRect(rect, bounds) {
  const minSize = 40;
  const width = Math.max(minSize, Math.min(rect.width, bounds.width));
  const height = Math.max(minSize, Math.min(rect.height, bounds.height));
  const left = Math.max(bounds.left, Math.min(rect.left, bounds.left + bounds.width - width));
  const top = Math.max(bounds.top, Math.min(rect.top, bounds.top + bounds.height - height));

  return { left, top, width, height };
}

function updateCropOverlayMask(crop) {
  const rect = getCropBoxRect(crop.box);
  const overlayWidth = crop.imageBounds.width;
  const overlayHeight = crop.imageBounds.height;

  crop.overlay.style.background = `
    linear-gradient(#0008, #0008) 0 0 / 100% ${rect.top}px no-repeat,
    linear-gradient(#0008, #0008) 0 ${rect.top + rect.height}px / 100% ${Math.max(0, overlayHeight - rect.top - rect.height)}px no-repeat,
    linear-gradient(#0008, #0008) 0 ${rect.top}px / ${rect.left}px ${rect.height}px no-repeat,
    linear-gradient(#0008, #0008) ${rect.left + rect.width}px ${rect.top}px / ${Math.max(0, overlayWidth - rect.left - rect.width)}px ${rect.height}px no-repeat
  `;
}

function cancelGraphImageCrop() {
  if (!activeCrop) return;

  activeCrop.overlay.remove();
  activeCrop.img.classList.remove("is-cropping");
  activeCrop.slot.classList.remove("is-cropping");
  activeCrop = null;
}

function applyGraphImageCrop() {
  if (!activeCrop) return;

  const { img, box, imageBounds } = activeCrop;
  if (!img.naturalWidth || !img.naturalHeight) return;

  const rect = getCropBoxRect(box);
  const scaleX = img.naturalWidth / imageBounds.width;
  const scaleY = img.naturalHeight / imageBounds.height;
  const sourceX = Math.max(0, Math.round(rect.left * scaleX));
  const sourceY = Math.max(0, Math.round(rect.top * scaleY));
  const sourceWidth = Math.max(1, Math.round(rect.width * scaleX));
  const sourceHeight = Math.max(1, Math.round(rect.height * scaleY));
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");

  if (!context) return;

  canvas.width = sourceWidth;
  canvas.height = sourceHeight;
  context.drawImage(img, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, sourceWidth, sourceHeight);

  const croppedSrc = canvas.toDataURL("image/png");
  cancelGraphImageCrop();
  setGraphImageWithHistory(img, croppedSrc);
  selectGraphImage(img);
}

function startGraphImageCrop(img) {
  if (!hasLoadedGraphImage(img)) return;

  cancelGraphImageCrop();

  const slot = img.closest(".graph-image-slot");
  if (!slot) return;

  const imageBounds = getImageBoxInSlot(img, slot);
  const overlay = document.createElement("div");
  const box = document.createElement("div");
  const handles = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
  const initialRect = {
    left: 0,
    top: 0,
    width: imageBounds.width,
    height: imageBounds.height
  };

  overlay.className = "graph-crop-overlay";
  overlay.style.left = `${imageBounds.left}px`;
  overlay.style.top = `${imageBounds.top}px`;
  overlay.style.width = `${imageBounds.width}px`;
  overlay.style.height = `${imageBounds.height}px`;
  box.className = "graph-crop-box";
  box.tabIndex = 0;

  handles.forEach(handle => {
    const node = document.createElement("span");
    node.className = `graph-crop-handle graph-crop-handle-${handle}`;
    node.dataset.handle = handle;
    box.appendChild(node);
  });

  overlay.appendChild(box);
  slot.appendChild(overlay);
  img.classList.add("is-cropping");
  slot.classList.add("is-cropping");

  activeCrop = {
    img,
    slot,
    overlay,
    box,
    imageBounds: {
      left: 0,
      top: 0,
      width: imageBounds.width,
      height: imageBounds.height
    }
  };
  setCropBoxRect(box, initialRect);
  updateCropOverlayMask(activeCrop);
  box.focus();

  let dragState = null;

  function beginDrag(event) {
    const handle = event.target.dataset.handle || "move";
    const startRect = getCropBoxRect(box);

    event.preventDefault();
    event.stopPropagation();

    dragState = {
      handle,
      startX: event.clientX,
      startY: event.clientY,
      startRect
    };

    document.addEventListener("pointermove", onDrag);
    document.addEventListener("pointerup", endDrag, { once: true });
  }

  function onDrag(event) {
    if (!dragState) return;

    const dx = event.clientX - dragState.startX;
    const dy = event.clientY - dragState.startY;
    const rect = { ...dragState.startRect };
    const handle = dragState.handle;

    if (handle === "move") {
      rect.left += dx;
      rect.top += dy;
    } else {
      if (handle.includes("w")) {
        rect.left += dx;
        rect.width -= dx;
      }

      if (handle.includes("e")) {
        rect.width += dx;
      }

      if (handle.includes("n")) {
        rect.top += dy;
        rect.height -= dy;
      }

      if (handle.includes("s")) {
        rect.height += dy;
      }
    }

    setCropBoxRect(box, clampCropRect(rect, activeCrop.imageBounds));
    updateCropOverlayMask(activeCrop);
  }

  function endDrag() {
    dragState = null;
    document.removeEventListener("pointermove", onDrag);
  }

  box.addEventListener("pointerdown", beginDrag);
}

function showGraphImageContextMenu(event, img) {
  if (!hasLoadedGraphImage(img)) return;

  event.preventDefault();
  selectGraphImage(img);

  if (!graphImageContextMenu) {
    graphImageContextMenu = createGraphImageContextMenu();
  }

  graphImageContextMenu.style.left = `${event.clientX}px`;
  graphImageContextMenu.style.top = `${event.clientY}px`;
  graphImageContextMenu.hidden = false;
}

export function initializeGraphImageControls() {
  const imageSlots = document.querySelectorAll(".graph-image-slot");

  imageSlots.forEach(slot => {
    const input = slot.querySelector(".graph-image-input");
    const img = slot.querySelector(".graph-image");

    input.addEventListener("change", event => {
      const file = event.target.files && event.target.files[0];
      loadGraphImageFile(slot, file);
      event.target.value = "";
    });

    slot.addEventListener("dragover", event => {
      event.preventDefault();
      slot.classList.add("is-drag-over");
    });

    slot.addEventListener("dragleave", event => {
      if (!slot.contains(event.relatedTarget)) {
        slot.classList.remove("is-drag-over");
      }
    });

    slot.addEventListener("drop", event => {
      event.preventDefault();
      slot.classList.remove("is-drag-over");
      loadGraphImageFile(slot, getImageFileFromDataTransfer(event.dataTransfer));
    });

    slot.addEventListener("paste", event => {
      const file = getImageFileFromDataTransfer(event.clipboardData);

      if (!file) return;

      event.preventDefault();
      loadGraphImageFile(slot, file);
    });

    img.addEventListener("click", event => {
      event.stopPropagation();
      selectGraphImage(img);
      hideGraphImageContextMenu();
    });

    img.addEventListener("contextmenu", event => {
      showGraphImageContextMenu(event, img);
    });

    img.addEventListener("keydown", event => {
      if (event.key !== "Backspace" && event.key !== "Delete") return;

      event.preventDefault();
      removeGraphImage(img);
      hideGraphImageContextMenu();
    });
  });

  document.addEventListener("click", event => {
    if (graphImageContextMenu?.contains(event.target)) return;
    if (activeCrop && activeCrop.overlay.contains(event.target)) return;

    hideGraphImageContextMenu();

    if (!event.target.closest(".graph-image")) {
      clearSelectedGraphImage();
    }
  });

  document.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
      if (!activeCrop && isTextEditingElement(document.activeElement)) {
        return;
      }

      if (undoLastGraphImageChange()) {
        event.preventDefault();
        hideGraphImageContextMenu();
        cancelGraphImageCrop();
      }
      return;
    }

    if (activeCrop) {
      if (event.key === "Enter") {
        event.preventDefault();
        applyGraphImageCrop();
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        cancelGraphImageCrop();
        return;
      }
    }

    if (event.key === "Escape") {
      hideGraphImageContextMenu();
      clearSelectedGraphImage();
      return;
    }

    if (event.key !== "Backspace" && event.key !== "Delete") return;
    if (!selectedGraphImage || document.activeElement !== selectedGraphImage) return;

    event.preventDefault();
    removeGraphImage(selectedGraphImage);
    hideGraphImageContextMenu();
  });
}

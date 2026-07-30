(function () {
  const history = [];
  let initialized = false;
  let selectedImage = null;
  let contextMenu = null;
  let activeCrop = null;
  let reportDate = new Date();
  let rainReportDate = null;
  let rainDateWasChanged = false;
  let temperatureReportDate = null;
  let temperatureDateWasChanged = false;
  let datePicker = null;
  let datePickerState = null;
  const monthNames = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
  ];
  const shortMonthNames = [
    "Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"
  ];
  const weekDays = ["Do", "Lu", "Ma", "Mi", "Ju", "Vi", "Sa"];
  const flowThresholds = {
    tomebamba: { normalMaximum: 29, alertMinimum: 50 },
    yanuncay: { normalMaximum: 32, alertMinimum: 50 },
    tarqui: { normalMaximum: 15, alertMinimum: 30 },
    machangara: { normalMaximum: 19, alertMinimum: 50 }
  };
  const rainMapParameterDefaults = Object.freeze({
    searchRadius: 10,
    p: 2,
    gridResolution: 0.1,
    nRound: 2,
    plotLogo: true,
    plotDesign: true
  });
  function padNumber(value) {
    return String(value).padStart(2, "0");
  }

  function formatPageDate(date) {
    return `${padNumber(date.getDate())}-${shortMonthNames[date.getMonth()]}-${String(date.getFullYear()).slice(-2)}`;
  }

  function formatPageTime(date) {
    return `${padNumber(date.getHours())}h${padNumber(date.getMinutes())}`;
  }

  function formatCalendarDay(date) {
    return `${date.getFullYear()}-${padNumber(date.getMonth() + 1)}-${padNumber(date.getDate())}`;
  }

  function formatCalendarDateTime(date) {
    return `${formatCalendarDay(date)} ${padNumber(date.getHours())}:${padNumber(date.getMinutes())}`;
  }

  function parseCalendarDay(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!match) return null;
    const parsed = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    return (
      parsed.getFullYear() === Number(match[1]) &&
      parsed.getMonth() === Number(match[2]) - 1 &&
      parsed.getDate() === Number(match[3])
    ) ? parsed : null;
  }

  function parseCalendarDateTime(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2}) ([01]\d|2[0-3]):([0-5]\d)$/.exec(value);
    if (!match) return null;
    const parsed = new Date(
      Number(match[1]),
      Number(match[2]) - 1,
      Number(match[3]),
      Number(match[4]),
      Number(match[5])
    );
    return (
      parsed.getFullYear() === Number(match[1]) &&
      parsed.getMonth() === Number(match[2]) - 1 &&
      parsed.getDate() === Number(match[3])
    ) ? parsed : null;
  }

  function updatePageDateTimes() {
    const dateText = formatPageDate(reportDate);
    const timeText = formatPageTime(reportDate);
    document.querySelectorAll("#report-hydromet-network-view .hydromet-page-date")
      .forEach((element) => { element.textContent = dateText; });
    document.querySelectorAll("#report-hydromet-network-view .hydromet-page-time")
      .forEach((element) => { element.textContent = timeText; });
    const rainDateInput = document.querySelector("[data-hydromet-rain-date]");
    if (!rainDateWasChanged) {
      rainReportDate = new Date(
        reportDate.getFullYear(),
        reportDate.getMonth(),
        reportDate.getDate()
      );
      if (rainDateInput) rainDateInput.value = formatCalendarDay(rainReportDate);
    }
    const temperatureDateInput = document.querySelector("[data-hydromet-temperature-date]");
    if (!temperatureDateWasChanged) {
      temperatureReportDate = new Date(reportDate);
      if (temperatureDateInput) {
        temperatureDateInput.value = formatCalendarDateTime(temperatureReportDate);
      }
    }
    const triggerValue = document.querySelector("#hydromet-datetime-trigger-value");
    if (triggerValue) triggerValue.textContent = `${dateText} · ${timeText}`;
  }

  function createDatePicker() {
    const picker = document.createElement("div");
    picker.className = "hydromet-date-picker";
    picker.hidden = true;
    picker.setAttribute("role", "dialog");
    picker.setAttribute("aria-label", "Seleccionar fecha y hora del reporte");
    picker.innerHTML = `
      <div class="hydromet-date-picker-header">
        <button class="hydromet-date-picker-nav" type="button" data-date-action="previous" aria-label="Mes anterior">‹</button>
        <div class="hydromet-date-picker-month"></div>
        <button class="hydromet-date-picker-nav" type="button" data-date-action="next" aria-label="Mes siguiente">›</button>
      </div>
      <div class="hydromet-date-picker-content">
        <div class="hydromet-date-calendar">
          <div class="hydromet-date-weekdays"></div>
          <div class="hydromet-date-days"></div>
        </div>
        <div class="hydromet-time-picker">
          <label class="hydromet-time-field">
            <span>Hora</span>
            <select data-time-unit="hour" aria-label="Hora"></select>
          </label>
          <label class="hydromet-time-field">
            <span>Minutos</span>
            <select data-time-unit="minute" aria-label="Minutos"></select>
          </label>
        </div>
      </div>
      <div class="hydromet-date-picker-footer">
        <button type="button" data-date-action="today">Hoy</button>
        <button type="button" data-date-action="cancel">Cancelar</button>
        <button type="button" data-date-action="apply">Aplicar</button>
      </div>
    `;
    picker.addEventListener("click", handleDatePickerClick);
    picker.addEventListener("change", handleTimePickerChange);
    document.body.appendChild(picker);
    return picker;
  }

  function getDatePickerState(date) {
    return {
      viewYear: date.getFullYear(),
      viewMonth: date.getMonth(),
      selectedDate: new Date(date.getFullYear(), date.getMonth(), date.getDate()),
      hour: date.getHours(),
      minute: date.getMinutes()
    };
  }

  function renderDatePicker() {
    if (!datePicker || !datePickerState) return;
    const month = datePicker.querySelector(".hydromet-date-picker-month");
    const weekdays = datePicker.querySelector(".hydromet-date-weekdays");
    const days = datePicker.querySelector(".hydromet-date-days");
    const hourSelect = datePicker.querySelector('[data-time-unit="hour"]');
    const minuteSelect = datePicker.querySelector('[data-time-unit="minute"]');
    month.textContent = `${monthNames[datePickerState.viewMonth]} ${datePickerState.viewYear}`;
    weekdays.innerHTML = weekDays.map((day) => `<span>${day}</span>`).join("");

    const firstDay = new Date(datePickerState.viewYear, datePickerState.viewMonth, 1);
    const startDate = new Date(
      datePickerState.viewYear,
      datePickerState.viewMonth,
      1 - firstDay.getDay()
    );
    const today = new Date();
    const selectedTime = datePickerState.selectedDate.getTime();
    const buttons = [];
    for (let index = 0; index < 42; index += 1) {
      const date = new Date(startDate);
      date.setDate(startDate.getDate() + index);
      const outside = date.getMonth() !== datePickerState.viewMonth;
      const isToday = date.toDateString() === today.toDateString();
      const selected = date.getTime() === selectedTime;
      buttons.push(`
        <button
          class="hydromet-date-day${outside ? " is-muted" : ""}${isToday ? " is-today" : ""}${selected ? " is-selected" : ""}"
          type="button"
          data-calendar-day="${formatCalendarDay(date)}"
        >${date.getDate()}</button>
      `);
    }
    days.innerHTML = buttons.join("");
    hourSelect.innerHTML = Array.from({ length: 24 }, (_, hour) => (
      `<option value="${hour}"${hour === datePickerState.hour ? " selected" : ""}>${padNumber(hour)}</option>`
    )).join("");
    minuteSelect.innerHTML = Array.from({ length: 60 }, (_, minute) => (
      `<option value="${minute}"${minute === datePickerState.minute ? " selected" : ""}>${padNumber(minute)}</option>`
    )).join("");
  }

  function positionDatePicker() {
    const trigger = document.querySelector("#hydromet-datetime-trigger");
    if (!datePicker || !trigger || datePicker.hidden) return;
    const triggerRect = trigger.getBoundingClientRect();
    const pickerRect = datePicker.getBoundingClientRect();
    const padding = 12;
    const left = Math.min(
      Math.max(triggerRect.right - pickerRect.width, padding),
      window.innerWidth - pickerRect.width - padding
    );
    const preferredTop = triggerRect.bottom + 8;
    const top = Math.min(
      preferredTop,
      window.innerHeight - pickerRect.height - padding
    );
    datePicker.style.left = `${left}px`;
    datePicker.style.top = `${Math.max(padding, top)}px`;
  }

  function openDatePicker() {
    if (!datePicker) datePicker = createDatePicker();
    datePickerState = getDatePickerState(reportDate);
    datePicker.hidden = false;
    document.querySelector("#hydromet-datetime-trigger")
      ?.setAttribute("aria-expanded", "true");
    renderDatePicker();
    positionDatePicker();
  }

  function closeDatePicker() {
    if (datePicker) datePicker.hidden = true;
    datePickerState = null;
    document.querySelector("#hydromet-datetime-trigger")
      ?.setAttribute("aria-expanded", "false");
  }

  function applyDatePicker() {
    if (!datePickerState) return;
    reportDate = new Date(
      datePickerState.selectedDate.getFullYear(),
      datePickerState.selectedDate.getMonth(),
      datePickerState.selectedDate.getDate(),
      datePickerState.hour,
      datePickerState.minute
    );
    updatePageDateTimes();
    closeDatePicker();
  }

  function handleDatePickerClick(event) {
    if (!datePickerState) return;
    const action = event.target.closest("[data-date-action]")?.dataset.dateAction;
    const dayValue = event.target.closest("[data-calendar-day]")?.dataset.calendarDay;
    if (action === "previous" || action === "next") {
      datePickerState.viewMonth += action === "previous" ? -1 : 1;
      if (datePickerState.viewMonth < 0) {
        datePickerState.viewMonth = 11;
        datePickerState.viewYear -= 1;
      } else if (datePickerState.viewMonth > 11) {
        datePickerState.viewMonth = 0;
        datePickerState.viewYear += 1;
      }
      renderDatePicker();
      return;
    }
    if (action === "today") {
      const today = new Date();
      datePickerState = getDatePickerState(today);
      renderDatePicker();
      return;
    }
    if (action === "cancel") {
      closeDatePicker();
      return;
    }
    if (action === "apply") {
      applyDatePicker();
      return;
    }
    if (dayValue) {
      const [year, month, day] = dayValue.split("-").map(Number);
      datePickerState.selectedDate = new Date(year, month - 1, day);
      datePickerState.viewYear = year;
      datePickerState.viewMonth = month - 1;
      renderDatePicker();
    }
  }

  function handleTimePickerChange(event) {
    if (!datePickerState) return;
    const unit = event.target.dataset.timeUnit;
    const value = Number(event.target.value);
    if (unit === "hour") datePickerState.hour = value;
    if (unit === "minute") datePickerState.minute = value;
  }

  function initializeDateTimeControl() {
    reportDate.setSeconds(0, 0);
    updatePageDateTimes();
    document.querySelector("#hydromet-datetime-trigger")
      ?.addEventListener("click", openDatePicker);
    document.addEventListener("pointerdown", (event) => {
      if (!datePicker || datePicker.hidden) return;
      if (datePicker.contains(event.target) ||
          event.target.closest("#hydromet-datetime-trigger")) return;
      closeDatePicker();
    });
    window.addEventListener("resize", closeDatePicker);
  }

  function selectReportTab(tabName, focusTab = false) {
    const tabs = Array.from(document.querySelectorAll(
      "#report-hydromet-network-view [data-hydromet-report-tab]"
    ));
    const panels = document.querySelectorAll(
      "#report-hydromet-network-view [data-hydromet-report-panel]"
    );
    tabs.forEach((tab) => {
      const active = tab.dataset.hydrometReportTab === tabName;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active && focusTab) tab.focus();
    });
    panels.forEach((panel) => {
      const active = panel.dataset.hydrometReportPanel === tabName;
      panel.classList.toggle("is-active", active);
      panel.hidden = !active;
    });
    const designActions = document.querySelector(".hydromet-report-toolbar-actions");
    if (designActions) designActions.hidden = tabName !== "design";
    if (tabName !== "graphics") {
      closeDatePicker();
      closeRainMapParameters();
    }
  }

  function initializeReportTabs() {
    const tabs = Array.from(document.querySelectorAll(
      "#report-hydromet-network-view [data-hydromet-report-tab]"
    ));
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => selectReportTab(tab.dataset.hydrometReportTab));
      tab.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();
        const direction = event.key === "ArrowRight" ? 1 : -1;
        const nextIndex = (index + direction + tabs.length) % tabs.length;
        selectReportTab(tabs[nextIndex].dataset.hydrometReportTab, true);
      });
    });
    selectReportTab("design");
  }

  function syncFlowReportValue(input) {
    const key = input?.dataset.flowInput;
    if (!key) return;
    const value = (input.textContent || "").replace(/\s+/g, " ").trim();
    const numericMatch = value.replace(",", ".").match(/-?\d+(?:\.\d+)?/);
    const numericValue = numericMatch ? Number(numericMatch[0]) : Number.NaN;
    const threshold = flowThresholds[key];
    let status = "";
    if (Number.isFinite(numericValue) && threshold) {
      if (numericValue <= threshold.normalMaximum) status = "normal";
      else if (numericValue >= threshold.alertMinimum) status = "alert";
      else status = "prealert";
    }
    const statusLabel = {
      normal: "normal",
      prealert: "prealerta",
      alert: "alerta"
    }[status] || "—";
    document.querySelectorAll(`[data-flow-output="${key}"]`).forEach((output) => {
      const row = output.closest(".hydromet-flow-report-row");
      const state = row?.querySelector(".hydromet-flow-state");
      output.textContent = value || "—";
      if (state) state.textContent = statusLabel;
      row?.classList.toggle("is-normal", status === "normal");
      row?.classList.toggle("is-prealert", status === "prealert");
      row?.classList.toggle("is-alert", status === "alert");
    });
  }

  function readRainObservations(card) {
    const observations = {};
    card.querySelectorAll(".hydromet-data-table tbody tr").forEach((row) => {
      const cells = row.querySelectorAll("td");
      const station = (cells[0]?.textContent || "").trim();
      const valueCell = cells[1];
      if (!station || station === "Date" || !valueCell?.hasAttribute("contenteditable")) return;
      const rawValue = (valueCell.textContent || "").trim().replace(",", ".");
      if (!rawValue) {
        observations[station] = null;
        return;
      }
      if (!/^\d+(?:\.\d+)?$/.test(rawValue)) {
        throw new Error(`El valor de ${station} no es un número válido.`);
      }
      const value = Number(rawValue);
      if (!Number.isFinite(value) || value < 0 || value > 2000) {
        throw new Error(`El valor de ${station} debe estar entre 0 y 2000 mm.`);
      }
      observations[station] = value;
    });
    return observations;
  }

  function readTemperatureObservations(card) {
    const observations = {};
    card.querySelectorAll(".hydromet-data-table tbody tr").forEach((row) => {
      const cells = row.querySelectorAll("td");
      const station = (cells[0]?.textContent || "").trim();
      const valueCell = cells[1];
      if (!station || !valueCell?.hasAttribute("contenteditable")) return;
      const rawValue = (valueCell.textContent || "").trim().replace(",", ".");
      if (!rawValue) {
        observations[station] = null;
        return;
      }
      if (!/^-?\d+(?:\.\d+)?$/.test(rawValue)) {
        throw new Error(`El valor de ${station} no es un número válido.`);
      }
      const value = Number(rawValue);
      if (!Number.isFinite(value) || value < -40 || value > 60) {
        throw new Error(`El valor de ${station} debe estar entre -40 y 60 °C.`);
      }
      observations[station] = value;
    });
    return observations;
  }

  function clearRainObservations(card) {
    card.querySelectorAll('.hydromet-data-table td[contenteditable="true"]')
      .forEach((cell) => {
        cell.textContent = "";
      });
    updateRainSummary(card);
    const firstCell = card.querySelector('.hydromet-data-table td[contenteditable="true"]');
    firstCell?.focus();
  }

  function clearTemperatureObservations(card) {
    card.querySelectorAll('.hydromet-data-table td[contenteditable="true"]')
      .forEach((cell) => { cell.textContent = ""; });
    card.querySelector('.hydromet-data-table td[contenteditable="true"]')?.focus();
  }

  function updateRainSummary(card) {
    const values = Array.from(
      card.querySelectorAll('.hydromet-data-table td[contenteditable="true"]')
    ).map((cell) => (cell.textContent || "").trim().replace(",", "."))
      .filter((value) => value !== "" && Number.isFinite(Number(value)))
      .map(Number);
    const filled = card.querySelector("[data-hydromet-rain-filled]");
    const average = card.querySelector("[data-hydromet-rain-average]");
    if (filled) filled.textContent = String(values.length);
    if (average) {
      average.textContent = values.length
        ? (values.reduce((total, value) => total + value, 0) / values.length).toFixed(2)
        : "0.00";
    }
  }

  function closeRainMapParameters() {
    const trigger = document.querySelector('[data-hydromet-params-trigger="rainfall"]');
    const panel = document.querySelector('[data-hydromet-params="rainfall"]');
    if (panel) panel.hidden = true;
    trigger?.setAttribute("aria-expanded", "false");
  }

  function positionRainMapParameters() {
    const trigger = document.querySelector('[data-hydromet-params-trigger="rainfall"]');
    const panel = document.querySelector('[data-hydromet-params="rainfall"]');
    if (!trigger || !panel || panel.hidden) return;
    const triggerRect = trigger.getBoundingClientRect();
    const panelRect = panel.getBoundingClientRect();
    const padding = 10;
    const left = Math.min(
      Math.max(triggerRect.left, padding),
      window.innerWidth - panelRect.width - padding
    );
    let top = triggerRect.bottom + 8;
    if (top + panelRect.height > window.innerHeight - padding) {
      top = Math.max(padding, triggerRect.top - panelRect.height - 8);
    }
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
  }

  function toggleRainMapParameters() {
    const trigger = document.querySelector('[data-hydromet-params-trigger="rainfall"]');
    const panel = document.querySelector('[data-hydromet-params="rainfall"]');
    if (!trigger || !panel) return;
    const shouldOpen = panel.hidden;
    panel.hidden = !shouldOpen;
    trigger.setAttribute("aria-expanded", String(shouldOpen));
    if (shouldOpen) {
      positionRainMapParameters();
      panel.querySelector("input")?.focus({ preventScroll: true });
    }
  }

  function resetRainMapParameters() {
    const panel = document.querySelector('[data-hydromet-params="rainfall"]');
    if (!panel) return;
    const values = {
      search_radius: rainMapParameterDefaults.searchRadius,
      p: rainMapParameterDefaults.p,
      grid_resolution: rainMapParameterDefaults.gridResolution,
      n_round: rainMapParameterDefaults.nRound
    };
    Object.entries(values).forEach(([name, value]) => {
      const input = panel.querySelector(`[name="${name}"]`);
      if (input) input.value = String(value);
    });
    const plotLogo = panel.querySelector('[name="plot_logo"]');
    const plotDesign = panel.querySelector('[name="plot_design"]');
    if (plotLogo) plotLogo.checked = rainMapParameterDefaults.plotLogo;
    if (plotDesign) plotDesign.checked = rainMapParameterDefaults.plotDesign;
  }

  function readRainMapParameters() {
    const panel = document.querySelector('[data-hydromet-params="rainfall"]');
    if (!panel) return { ...rainMapParameterDefaults };
    const numberFields = [
      ["search_radius", "searchRadius", 1, 100, false],
      ["p", "p", 0.1, 10, false],
      ["grid_resolution", "gridResolution", 0.02, 5, false],
      ["n_round", "nRound", 0, 6, true]
    ];
    const parameters = {};
    numberFields.forEach(([name, key, minimum, maximum, integerOnly]) => {
      const input = panel.querySelector(`[name="${name}"]`);
      const value = Number(input?.value);
      if (!Number.isFinite(value) || value < minimum || value > maximum ||
          (integerOnly && !Number.isInteger(value))) {
        throw new Error(
          `${name} debe ser ${integerOnly ? "un entero " : ""}entre ${minimum} y ${maximum}.`
        );
      }
      parameters[key] = value;
    });
    parameters.plotLogo = Boolean(panel.querySelector('[name="plot_logo"]')?.checked);
    parameters.plotDesign = Boolean(panel.querySelector('[name="plot_design"]')?.checked);
    return parameters;
  }

  function initializeRainMapParameters() {
    const trigger = document.querySelector('[data-hydromet-params-trigger="rainfall"]');
    const panel = document.querySelector('[data-hydromet-params="rainfall"]');
    if (!trigger || !panel) return;
    document.body.appendChild(panel);
    trigger.addEventListener("click", toggleRainMapParameters);
    panel.querySelector("[data-hydromet-params-close]")
      ?.addEventListener("click", closeRainMapParameters);
    panel.querySelector("[data-hydromet-params-reset]")
      ?.addEventListener("click", resetRainMapParameters);
    document.addEventListener("pointerdown", (event) => {
      if (panel.hidden || panel.contains(event.target) || trigger.contains(event.target)) return;
      closeRainMapParameters();
    });
    window.addEventListener("resize", positionRainMapParameters);
    document.addEventListener("scroll", positionRainMapParameters, true);
  }

  function closeTemperatureMapParameters() {
    const trigger = document.querySelector('[data-hydromet-params-trigger="temperatures"]');
    const panel = document.querySelector('[data-hydromet-params="temperatures"]');
    if (panel) panel.hidden = true;
    trigger?.setAttribute("aria-expanded", "false");
  }

  function positionTemperatureMapParameters() {
    const trigger = document.querySelector('[data-hydromet-params-trigger="temperatures"]');
    const panel = document.querySelector('[data-hydromet-params="temperatures"]');
    if (!trigger || !panel || panel.hidden) return;
    const triggerRect = trigger.getBoundingClientRect();
    const panelRect = panel.getBoundingClientRect();
    const padding = 10;
    panel.style.left = `${Math.min(
      Math.max(triggerRect.left, padding),
      Math.max(padding, window.innerWidth - panelRect.width - padding)
    )}px`;
    let top = triggerRect.bottom + 8;
    if (top + panelRect.height > window.innerHeight - padding) {
      top = Math.max(padding, triggerRect.top - panelRect.height - 8);
    }
    panel.style.top = `${top}px`;
  }

  function resetTemperatureMapParameters() {
    const panel = document.querySelector('[data-hydromet-params="temperatures"]');
    if (!panel) return;
    const values = { search_radius: 10, p: 2, grid_resolution: 0.1, n_round: 2 };
    Object.entries(values).forEach(([name, value]) => {
      const input = panel.querySelector(`[name="${name}"]`);
      if (input) input.value = String(value);
    });
  }

  function readTemperatureMapParameters() {
    const panel = document.querySelector('[data-hydromet-params="temperatures"]');
    const fields = [
      ["search_radius", "searchRadius", 1, 100, false],
      ["p", "p", 0.1, 10, false],
      ["grid_resolution", "gridResolution", 0.02, 5, false],
      ["n_round", "nRound", 0, 6, true]
    ];
    const parameters = {};
    fields.forEach(([name, key, minimum, maximum, integerOnly]) => {
      const value = Number(panel?.querySelector(`[name="${name}"]`)?.value);
      if (!Number.isFinite(value) || value < minimum || value > maximum ||
          (integerOnly && !Number.isInteger(value))) {
        throw new Error(
          `${name} debe ser ${integerOnly ? "un entero " : ""}entre ${minimum} y ${maximum}.`
        );
      }
      parameters[key] = value;
    });
    return parameters;
  }

  function initializeTemperatureMapParameters() {
    const trigger = document.querySelector('[data-hydromet-params-trigger="temperatures"]');
    const panel = document.querySelector('[data-hydromet-params="temperatures"]');
    if (!trigger || !panel) return;
    document.body.appendChild(panel);
    trigger.addEventListener("click", () => {
      const shouldOpen = panel.hidden;
      panel.hidden = !shouldOpen;
      trigger.setAttribute("aria-expanded", String(shouldOpen));
      if (shouldOpen) {
        positionTemperatureMapParameters();
        panel.querySelector("input")?.focus({ preventScroll: true });
      }
    });
    panel.querySelector("[data-hydromet-params-close]")
      ?.addEventListener("click", closeTemperatureMapParameters);
    panel.querySelector("[data-hydromet-params-reset]")
      ?.addEventListener("click", resetTemperatureMapParameters);
    document.addEventListener("pointerdown", (event) => {
      if (panel.hidden || panel.contains(event.target) || trigger.contains(event.target)) return;
      closeTemperatureMapParameters();
    });
    window.addEventListener("resize", positionTemperatureMapParameters);
    document.addEventListener("scroll", positionTemperatureMapParameters, true);
  }

  async function responseJson(response) {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "No fue posible generar el mapa de lluvias.");
    }
    return payload;
  }

  function initializeDesignExport() {
    window.NotasHydrometDesignExport.init({
      getReportDate: () => reportDate,
      formatCalendarDay,
      padNumber,
      cancelCrop,
      clearSelection
    });
  }

  function setRunState(button, message, isError = false) {
    const group = button.dataset.hydrometRun;
    const status = document.querySelector(`[data-hydromet-run-status="${group}"]`);
    if (status) {
      status.textContent = message;
      status.classList.toggle("is-error", isError);
    }
  }

  function setRainDesignStatus(visible, message = "Generando mapa…") {
    const status = document.querySelector("[data-hydromet-rain-map-design-status]");
    if (!status) return;
    status.textContent = message;
    status.hidden = !visible;
  }

  function placeGeneratedRainMap(imageUrl) {
    return new Promise((resolve, reject) => {
      const image = document.querySelector("[data-hydromet-rain-map-output]");
      if (!image) {
        reject(new Error("No se encontró el espacio del mapa en el diseño."));
        return;
      }
      image.onload = () => {
        image.hidden = false;
        resolve();
      };
      image.onerror = () => reject(new Error("El mapa se generó, pero no pudo cargarse en el diseño."));
      image.hidden = true;
      image.src = `${imageUrl}?v=${Date.now()}`;
    });
  }

  function placeRainMapPreview(imageUrl) {
    return new Promise((resolve, reject) => {
      const image = document.querySelector("[data-hydromet-rain-preview-output]");
      const empty = document.querySelector("[data-hydromet-rain-preview-empty]");
      if (!image) {
        reject(new Error("No se encontró la vista previa del mapa."));
        return;
      }
      image.onload = () => {
        image.hidden = false;
        if (empty) empty.hidden = true;
        resolve();
      };
      image.onerror = () => reject(new Error("No se pudo cargar la vista previa del mapa."));
      image.hidden = true;
      image.src = `${imageUrl}?v=${Date.now()}`;
    });
  }

  function setTemperatureDesignStatus(visible, message = "Generando mapa…") {
    const status = document.querySelector("[data-hydromet-temperature-map-design-status]");
    if (!status) return;
    status.textContent = message;
    status.hidden = !visible;
  }

  function placeGeneratedTemperatureMap(imageUrl) {
    return new Promise((resolve, reject) => {
      const image = document.querySelector("[data-hydromet-temperature-map-output]");
      if (!image) {
        reject(new Error("No se encontró el espacio del mapa de temperaturas en el diseño."));
        return;
      }
      image.onload = () => {
        image.hidden = false;
        resolve();
      };
      image.onerror = () => reject(
        new Error("El mapa se generó, pero no pudo cargarse en el diseño.")
      );
      image.hidden = true;
      image.src = `${imageUrl}?v=${Date.now()}`;
    });
  }

  function placeTemperatureMapPreview(imageUrl) {
    return new Promise((resolve, reject) => {
      const image = document.querySelector("[data-hydromet-temperature-preview-output]");
      const empty = document.querySelector("[data-hydromet-temperature-preview-empty]");
      if (!image) {
        reject(new Error("No se encontró la vista previa del mapa de temperaturas."));
        return;
      }
      image.onload = () => {
        image.hidden = false;
        if (empty) empty.hidden = true;
        resolve();
      };
      image.onerror = () => reject(new Error("No se pudo cargar la vista previa del mapa."));
      image.hidden = true;
      image.src = `${imageUrl}?v=${Date.now()}`;
    });
  }

  async function pollRainMap(jobId) {
    for (let attempt = 0; attempt < 600; attempt += 1) {
      const response = await fetch(
        `/api/reports/hydromet-network/rain-map/${encodeURIComponent(jobId)}`,
        { cache: "no-store", headers: { Accept: "application/json" } }
      );
      const job = await responseJson(response);
      if (job.status === "completed") return job;
      if (job.status === "failed") {
        throw new Error(job.error || "No fue posible generar el mapa de lluvias.");
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    throw new Error("La generación del mapa superó el tiempo máximo permitido.");
  }

  async function runRainMapGeneration(card, button) {
    if (button.disabled) return;
    const label = button.querySelector("[data-hydromet-run-label]");
    button.disabled = true;
    button.classList.add("is-running");
    button.setAttribute("aria-busy", "true");
    if (label) label.textContent = "Generando…";
    setRunState(button, "Procesando en segundo plano");
    setRainDesignStatus(true);
    try {
      const observations = readRainObservations(card);
      const parameters = readRainMapParameters();
      const startTime = card.querySelector("[data-hydromet-rain-start-time]")?.value || "";
      const endTime = card.querySelector("[data-hydromet-rain-end-time]")?.value || "";
      if (!/^\d{2}:\d{2}$/.test(startTime) || !/^\d{2}:\d{2}$/.test(endTime)) {
        throw new Error("Selecciona una hora inicial y una hora final.");
      }
      if (startTime >= endTime) {
        throw new Error("La hora final debe ser posterior a la hora inicial.");
      }
      closeRainMapParameters();
      const response = await fetch("/api/reports/hydromet-network/rain-map", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          reportDate: formatCalendarDay(rainReportDate || reportDate),
          startTime,
          endTime,
          observations,
          parameters,
        }),
      });
      const queued = await responseJson(response);
      const job = await pollRainMap(queued.jobId);
      await placeGeneratedRainMap(job.imageUrl);
      await placeRainMapPreview(job.previewUrl);
      setRainDesignStatus(false);
      setRunState(button, "Mapa listo y vista previa actualizada");
      window.dispatchEvent(new CustomEvent("agender:hydromet-run", {
        detail: { group: "rainfall", jobId: queued.jobId, imageUrl: job.imageUrl },
      }));
    } catch (error) {
      setRainDesignStatus(false);
      setRunState(button, error.message || "No fue posible generar el mapa.", true);
    } finally {
      button.disabled = false;
      button.classList.remove("is-running");
      button.removeAttribute("aria-busy");
      if (label) label.textContent = "Ejecutar";
    }
  }

  async function pollTemperatureMap(jobId) {
    for (let attempt = 0; attempt < 600; attempt += 1) {
      const response = await fetch(
        `/api/reports/hydromet-network/temperature-map/${encodeURIComponent(jobId)}`,
        { cache: "no-store", headers: { Accept: "application/json" } }
      );
      const job = await responseJson(response);
      if (job.status === "completed") return job;
      if (job.status === "failed") {
        throw new Error(job.error || "No fue posible generar el mapa de temperaturas.");
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    throw new Error("La generación del mapa superó el tiempo máximo permitido.");
  }

  async function runTemperatureMapGeneration(card, button) {
    if (button.disabled) return;
    const label = button.querySelector("[data-hydromet-run-label]");
    button.disabled = true;
    button.classList.add("is-running");
    button.setAttribute("aria-busy", "true");
    if (label) label.textContent = "Generando…";
    setRunState(button, "Procesando en segundo plano");
    setTemperatureDesignStatus(true);
    try {
      const observations = readTemperatureObservations(card);
      const parameters = readTemperatureMapParameters();
      const interpolationDate = parseCalendarDateTime(
        card.querySelector("[data-hydromet-temperature-date]")?.value || ""
      );
      const startTime = card.querySelector("[data-hydromet-temperature-start-time]")?.value || "";
      const endTime = card.querySelector("[data-hydromet-temperature-end-time]")?.value || "";
      if (!Object.values(observations).some((value) => value !== null)) {
        throw new Error("Ingresa al menos un valor de temperatura.");
      }
      if (!interpolationDate) {
        throw new Error("Ingresa la fecha y hora del registro como AAAA-MM-DD HH:mm.");
      }
      if (!/^\d{2}:\d{2}$/.test(startTime) || !/^\d{2}:\d{2}$/.test(endTime)) {
        throw new Error("Selecciona una hora inicial y una hora final.");
      }
      if (startTime >= endTime) {
        throw new Error("La hora final debe ser posterior a la hora inicial.");
      }
      closeTemperatureMapParameters();
      const response = await fetch("/api/reports/hydromet-network/temperature-map", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          dateInterpolation: `${formatCalendarDateTime(interpolationDate).replace(" ", "T")}:00`,
          startTime,
          endTime,
          observations,
          parameters,
        }),
      });
      const queued = await responseJson(response);
      const job = await pollTemperatureMap(queued.jobId);
      await placeGeneratedTemperatureMap(job.imageUrl);
      await placeTemperatureMapPreview(job.imageUrl);
      setTemperatureDesignStatus(false);
      setRunState(button, "Mapa listo en Diseño");
      window.dispatchEvent(new CustomEvent("agender:hydromet-run", {
        detail: { group: "temperatures", jobId: queued.jobId, imageUrl: job.imageUrl },
      }));
    } catch (error) {
      setTemperatureDesignStatus(false);
      setRunState(button, error.message || "No fue posible generar el mapa.", true);
    } finally {
      button.disabled = false;
      button.classList.remove("is-running");
      button.removeAttribute("aria-busy");
      if (label) label.textContent = "Ejecutar";
    }
  }

  function initializeGraphicsTables() {
    const cards = document.querySelectorAll(
      "#hydromet-panel-graphics [data-hydromet-data-table]"
    );
    cards.forEach((card) => {
      const table = card.querySelector(".hydromet-data-table");
      const trigger = card.querySelector(".hydromet-data-trigger");
      const panel = card.querySelector(".hydromet-data-panel");
      trigger?.addEventListener("click", () => {
        const shouldOpen = trigger.getAttribute("aria-expanded") !== "true";
        cards.forEach((otherCard) => {
          const otherTrigger = otherCard.querySelector(".hydromet-data-trigger");
          const otherPanel = otherCard.querySelector(".hydromet-data-panel");
          otherTrigger?.setAttribute("aria-expanded", "false");
          if (otherPanel) otherPanel.hidden = true;
        });
        trigger.setAttribute("aria-expanded", String(shouldOpen));
        if (panel) panel.hidden = !shouldOpen;
        if (shouldOpen) {
          panel?.querySelector('td[contenteditable="true"]')?.focus();
        }
      });
      table?.addEventListener("keydown", (event) => {
        const cell = event.target.closest('td[contenteditable="true"]');
        if (!cell || event.key !== "Enter") return;
        event.preventDefault();
        const valueCells = Array.from(table.querySelectorAll('td[contenteditable="true"]'));
        const nextCell = valueCells[valueCells.indexOf(cell) + 1];
        if (nextCell) nextCell.focus();
        else cell.blur();
      });
      table?.addEventListener("input", (event) => {
        if (event.target.matches("[data-flow-input]")) {
          syncFlowReportValue(event.target);
        }
        if (card.dataset.hydrometDataTable === "rainfall") {
          updateRainSummary(card);
        }
      });
      card.addEventListener("paste", (event) => {
        const editable = event.target.closest('[contenteditable="true"]');
        if (!editable) return;
        const text = event.clipboardData?.getData("text/plain");
        if (text === undefined) return;
        event.preventDefault();
        document.execCommand("insertText", false, text);
      });
      const runButton = card.querySelector("[data-hydromet-run]");
      runButton?.addEventListener("click", () => {
        if (runButton.dataset.hydrometRun === "rainfall") {
          runRainMapGeneration(card, runButton);
          return;
        }
        if (runButton.dataset.hydrometRun === "temperatures") {
          runTemperatureMapGeneration(card, runButton);
          return;
        }
        window.dispatchEvent(new CustomEvent("agender:hydromet-run", {
          detail: { group: runButton.dataset.hydrometRun },
        }));
      });
      const clearButton = card.querySelector("[data-hydromet-clear]");
      clearButton?.addEventListener("click", () => {
        if (clearButton.dataset.hydrometClear === "rainfall") {
          clearRainObservations(card);
        }
        if (clearButton.dataset.hydrometClear === "temperatures") {
          clearTemperatureObservations(card);
        }
      });
      if (card.dataset.hydrometDataTable === "rainfall") {
        const rainDateInput = card.querySelector("[data-hydromet-rain-date]");
        rainDateInput?.addEventListener("change", () => {
          const parsed = parseCalendarDay(rainDateInput.value);
          if (!parsed) {
            rainDateInput.value = formatCalendarDay(rainReportDate || reportDate);
            return;
          }
          rainReportDate = parsed;
          rainDateWasChanged = true;
        });
        const endTime = card.querySelector("[data-hydromet-rain-end-time]");
        if (endTime) {
          endTime.value = `${padNumber(reportDate.getHours())}:${padNumber(reportDate.getMinutes())}`;
        }
        updateRainSummary(card);
      }
      if (card.dataset.hydrometDataTable === "temperatures") {
        const dateInput = card.querySelector("[data-hydromet-temperature-date]");
        dateInput?.addEventListener("change", () => {
          const parsed = parseCalendarDateTime(dateInput.value);
          if (!parsed) {
            dateInput.value = formatCalendarDateTime(temperatureReportDate || reportDate);
            return;
          }
          temperatureReportDate = parsed;
          temperatureDateWasChanged = true;
        });
        const endTime = card.querySelector("[data-hydromet-temperature-end-time]");
        if (endTime) {
          endTime.value = `${padNumber(reportDate.getHours())}:${padNumber(reportDate.getMinutes())}`;
        }
      }
    });
    document.querySelectorAll("[data-flow-input]").forEach(syncFlowReportValue);
  }

  function getImageFile(dataTransfer) {
    if (!dataTransfer) return null;
    const directFile = Array.from(dataTransfer.files || [])
      .find((file) => file.type.startsWith("image/"));
    if (directFile) return directFile;
    const item = Array.from(dataTransfer.items || [])
      .find((entry) => entry.kind === "file" && entry.type.startsWith("image/"));
    return item ? item.getAsFile() : null;
  }

  function getSource(image) {
    return image && !image.hidden ? image.getAttribute("src") || "" : "";
  }

  function setImage(image, source, remember = true) {
    if (!image) return;
    if (remember) history.push({ image, source: getSource(image) });
    const slot = image.closest(".hydromet-image-slot");
    if (!slot) return;

    if (!source) {
      image.removeAttribute("src");
      image.hidden = true;
      image.classList.remove("is-selected");
      slot.classList.remove("has-image");
      if (selectedImage === image) selectedImage = null;
      return;
    }

    image.onload = () => {
      image.hidden = false;
      slot.classList.add("has-image");
    };
    image.onerror = () => setImage(image, "", false);
    image.src = source;
    image.hidden = false;
    slot.classList.add("has-image");
  }

  function loadFile(slot, file) {
    if (!slot || !file || !file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => {
      const image = slot.querySelector(".hydromet-inserted-image");
      setImage(image, reader.result);
      selectImage(image);
    };
    reader.onerror = () => console.error("No se pudo cargar la imagen seleccionada.");
    reader.readAsDataURL(file);
  }

  function selectImage(image) {
    if (selectedImage && selectedImage !== image) {
      selectedImage.classList.remove("is-selected");
    }
    selectedImage = image && !image.hidden ? image : null;
    if (selectedImage) {
      selectedImage.classList.add("is-selected");
      selectedImage.focus({ preventScroll: true });
    }
  }

  function clearSelection() {
    selectedImage?.classList.remove("is-selected");
    selectedImage = null;
  }

  function removeImage(image) {
    if (!image || image.hidden) return;
    const slot = image.closest(".hydromet-image-slot");
    cancelCrop();
    setImage(image, "");
    slot?.focus({ preventScroll: true });
  }

  function undoImageChange() {
    const previous = history.pop();
    if (!previous) return false;
    cancelCrop();
    setImage(previous.image, previous.source, false);
    if (previous.source) selectImage(previous.image);
    else clearSelection();
    return true;
  }

  function createContextMenu() {
    const menu = document.createElement("div");
    menu.className = "hydromet-image-menu";
    menu.hidden = true;
    menu.setAttribute("role", "menu");
    menu.innerHTML = `
      <button type="button" role="menuitem" data-hydromet-action="crop">Recortar imagen</button>
      <button type="button" role="menuitem" data-hydromet-action="replace">Cambiar imagen</button>
      <button type="button" role="menuitem" data-hydromet-action="remove">Eliminar imagen</button>
    `;
    menu.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-hydromet-action]");
      if (!button || !selectedImage) return;
      hideContextMenu();
      if (button.dataset.hydrometAction === "crop") {
        startCrop(selectedImage);
      } else if (button.dataset.hydrometAction === "replace") {
        selectedImage.closest(".hydromet-image-slot")
          ?.querySelector(".hydromet-image-input")
          ?.click();
      } else if (button.dataset.hydrometAction === "remove") {
        removeImage(selectedImage);
      }
    });
    document.body.appendChild(menu);
    return menu;
  }

  function showContextMenu(event, image) {
    if (!image || image.hidden) return;
    event.preventDefault();
    selectImage(image);
    if (!contextMenu) contextMenu = createContextMenu();
    contextMenu.hidden = false;
    const width = contextMenu.offsetWidth;
    const height = contextMenu.offsetHeight;
    contextMenu.style.left = `${Math.min(event.clientX, window.innerWidth - width - 8)}px`;
    contextMenu.style.top = `${Math.min(event.clientY, window.innerHeight - height - 8)}px`;
  }

  function hideContextMenu() {
    if (contextMenu) contextMenu.hidden = true;
  }

  function setCropRect(box, rect) {
    box.style.left = `${rect.left}px`;
    box.style.top = `${rect.top}px`;
    box.style.width = `${rect.width}px`;
    box.style.height = `${rect.height}px`;
  }

  function getCropRect(box) {
    return {
      left: parseFloat(box.style.left) || 0,
      top: parseFloat(box.style.top) || 0,
      width: parseFloat(box.style.width) || 0,
      height: parseFloat(box.style.height) || 0
    };
  }

  function clampCropRect(rect, bounds) {
    const minimum = Math.min(40, bounds.width, bounds.height);
    const width = Math.max(minimum, Math.min(rect.width, bounds.width));
    const height = Math.max(minimum, Math.min(rect.height, bounds.height));
    const left = Math.max(0, Math.min(rect.left, bounds.width - width));
    const top = Math.max(0, Math.min(rect.top, bounds.height - height));
    return { left, top, width, height };
  }

  function updateCropMask() {
    if (!activeCrop) return;
    const rect = getCropRect(activeCrop.box);
    const { width, height } = activeCrop.bounds;
    activeCrop.overlay.style.background = `
      linear-gradient(#0008, #0008) 0 0 / 100% ${rect.top}px no-repeat,
      linear-gradient(#0008, #0008) 0 ${rect.top + rect.height}px / 100% ${Math.max(0, height - rect.top - rect.height)}px no-repeat,
      linear-gradient(#0008, #0008) 0 ${rect.top}px / ${rect.left}px ${rect.height}px no-repeat,
      linear-gradient(#0008, #0008) ${rect.left + rect.width}px ${rect.top}px / ${Math.max(0, width - rect.left - rect.width)}px ${rect.height}px no-repeat
    `;
  }

  function cancelCrop() {
    if (!activeCrop) return;
    activeCrop.overlay.remove();
    activeCrop.slot.classList.remove("is-cropping");
    activeCrop = null;
  }

  function applyCrop() {
    if (!activeCrop) return;
    const { image, box, bounds } = activeCrop;
    if (!image.naturalWidth || !image.naturalHeight) return;
    const rect = getCropRect(box);
    const sourceX = Math.max(0, Math.round(rect.left * image.naturalWidth / bounds.width));
    const sourceY = Math.max(0, Math.round(rect.top * image.naturalHeight / bounds.height));
    const sourceWidth = Math.max(1, Math.round(rect.width * image.naturalWidth / bounds.width));
    const sourceHeight = Math.max(1, Math.round(rect.height * image.naturalHeight / bounds.height));
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    if (!context) return;
    canvas.width = sourceWidth;
    canvas.height = sourceHeight;
    context.drawImage(
      image,
      sourceX,
      sourceY,
      sourceWidth,
      sourceHeight,
      0,
      0,
      sourceWidth,
      sourceHeight
    );
    const croppedSource = canvas.toDataURL("image/png");
    cancelCrop();
    setImage(image, croppedSource);
    selectImage(image);
  }

  function startCrop(image) {
    if (!image || image.hidden) return;
    cancelCrop();
    const slot = image.closest(".hydromet-image-slot");
    if (!slot) return;
    const bounds = { width: image.offsetWidth, height: image.offsetHeight };
    if (!bounds.width || !bounds.height) return;
    const overlay = document.createElement("div");
    const box = document.createElement("div");
    const actions = document.createElement("div");
    overlay.className = "hydromet-crop-overlay";
    box.className = "hydromet-crop-box";
    box.tabIndex = 0;
    ["nw", "n", "ne", "e", "se", "s", "sw", "w"].forEach((direction) => {
      const handle = document.createElement("span");
      handle.className = `hydromet-crop-handle hydromet-crop-handle-${direction}`;
      handle.dataset.handle = direction;
      box.appendChild(handle);
    });
    actions.className = "hydromet-crop-actions";
    actions.innerHTML = `
      <button type="button" data-crop-action="cancel">Cancelar</button>
      <button type="button" data-crop-action="apply">Aplicar</button>
    `;
    overlay.append(box, actions);
    slot.appendChild(overlay);
    slot.classList.add("is-cropping");
    activeCrop = { image, slot, overlay, box, bounds };

    const insetX = Math.max(8, bounds.width * 0.05);
    const insetY = Math.max(8, bounds.height * 0.05);
    setCropRect(box, {
      left: insetX,
      top: insetY,
      width: bounds.width - insetX * 2,
      height: bounds.height - insetY * 2
    });
    updateCropMask();
    box.focus({ preventScroll: true });

    let drag = null;
    const move = (event) => {
      if (!drag || !activeCrop) return;
      const dx = event.clientX - drag.startX;
      const dy = event.clientY - drag.startY;
      const rect = { ...drag.rect };
      if (drag.handle === "move") {
        rect.left += dx;
        rect.top += dy;
      } else {
        if (drag.handle.includes("w")) {
          rect.left += dx;
          rect.width -= dx;
        }
        if (drag.handle.includes("e")) rect.width += dx;
        if (drag.handle.includes("n")) {
          rect.top += dy;
          rect.height -= dy;
        }
        if (drag.handle.includes("s")) rect.height += dy;
      }
      setCropRect(box, clampCropRect(rect, bounds));
      updateCropMask();
    };
    const stop = () => {
      drag = null;
      document.removeEventListener("pointermove", move);
    };
    box.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      event.stopPropagation();
      drag = {
        handle: event.target.dataset.handle || "move",
        startX: event.clientX,
        startY: event.clientY,
        rect: getCropRect(box)
      };
      document.addEventListener("pointermove", move);
      document.addEventListener("pointerup", stop, { once: true });
    });
    actions.addEventListener("click", (event) => {
      const action = event.target.closest("button")?.dataset.cropAction;
      if (action === "apply") applyCrop();
      if (action === "cancel") cancelCrop();
    });
  }

  function isEditingText() {
    const element = document.activeElement;
    return Boolean(
      element &&
      (element.isContentEditable ||
        element.tagName === "INPUT" ||
        element.tagName === "TEXTAREA" ||
        element.tagName === "SELECT")
    );
  }

  function initializeSlot(slot) {
    const input = slot.querySelector(".hydromet-image-input");
    const image = slot.querySelector(".hydromet-inserted-image");
    input.addEventListener("change", (event) => {
      loadFile(slot, event.target.files?.[0]);
      event.target.value = "";
    });
    slot.addEventListener("dragover", (event) => {
      event.preventDefault();
      slot.classList.add("is-drag-over");
    });
    slot.addEventListener("dragleave", (event) => {
      if (!slot.contains(event.relatedTarget)) slot.classList.remove("is-drag-over");
    });
    slot.addEventListener("drop", (event) => {
      event.preventDefault();
      slot.classList.remove("is-drag-over");
      loadFile(slot, getImageFile(event.dataTransfer));
    });
    slot.addEventListener("paste", (event) => {
      const file = getImageFile(event.clipboardData);
      if (!file) return;
      event.preventDefault();
      loadFile(slot, file);
    });
    slot.addEventListener("keydown", (event) => {
      if ((event.key === "Enter" || event.key === " ") && image.hidden) {
        event.preventDefault();
        input.click();
      }
    });
    image.addEventListener("click", (event) => {
      event.stopPropagation();
      selectImage(image);
      hideContextMenu();
    });
    image.addEventListener("contextmenu", (event) => showContextMenu(event, image));
  }

  function init() {
    if (initialized) return;
    const slots = document.querySelectorAll(
      "#report-hydromet-network-view .hydromet-image-slot"
    );
    if (!slots.length) return;
    initialized = true;
    initializeReportTabs();
    initializeGraphicsTables();
    initializeRainMapParameters();
    initializeTemperatureMapParameters();
    initializeDateTimeControl();
    initializeDesignExport();
    slots.forEach(initializeSlot);

    document.addEventListener("click", (event) => {
      if (contextMenu?.contains(event.target)) return;
      if (activeCrop?.overlay.contains(event.target)) return;
      hideContextMenu();
      if (!event.target.closest(".hydromet-inserted-image")) clearSelection();
    });
    document.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z" && !isEditingText()) {
        if (undoImageChange()) {
          event.preventDefault();
          hideContextMenu();
        }
        return;
      }
      if (activeCrop && event.key === "Enter") {
        event.preventDefault();
        applyCrop();
        return;
      }
      if (activeCrop && event.key === "Escape") {
        event.preventDefault();
        cancelCrop();
        return;
      }
      if (event.key === "Escape") {
        closeDatePicker();
        closeRainMapParameters();
        hideContextMenu();
        clearSelection();
        return;
      }
      if ((event.key === "Delete" || event.key === "Backspace") &&
          selectedImage &&
          document.activeElement === selectedImage) {
        event.preventDefault();
        removeImage(selectedImage);
        hideContextMenu();
      }
    });
  }

  window.NotasHydrometReport = { init };
})();

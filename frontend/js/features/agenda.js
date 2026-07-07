(function () {
  const EVENTS_KEY = "agender.agenda.events";
  const CATEGORIES = ["Reunion", "Entrega", "Revision", "Tramite", "Recordatorio", "Personal"];
  const { loadJson, saveJson } = window.NotasStorage;
  const { escapeHtml } = window.NotasUtils;

  let events = [];
  let viewDate;
  let selectedDate;
  let grid;
  let miniGrid;
  let monthTitle;
  let miniTitle;
  let dialog;
  let form;
  let dialogTitle;
  let deleteButton;
  let mapsButton;
  let fields;

  function initAgenda() {
    grid = document.querySelector("#agenda-grid");
    miniGrid = document.querySelector("#agenda-mini-grid");
    monthTitle = document.querySelector("#agenda-month-title");
    miniTitle = document.querySelector("#agenda-mini-title");
    dialog = document.querySelector("#agenda-event-dialog");
    form = document.querySelector("#agenda-event-form");
    dialogTitle = document.querySelector("#agenda-dialog-title");
    deleteButton = document.querySelector("#agenda-delete-event");
    mapsButton = document.querySelector("#agenda-open-maps");
    fields = {
      id: document.querySelector("#agenda-event-id"),
      title: document.querySelector("#agenda-event-title"),
      date: document.querySelector("#agenda-event-date"),
      startTime: document.querySelector("#agenda-event-start-time"),
      endTime: document.querySelector("#agenda-event-end-time"),
      category: document.querySelector("#agenda-event-category"),
      status: document.querySelector("#agenda-event-status"),
      location: document.querySelector("#agenda-event-location"),
      notes: document.querySelector("#agenda-event-notes")
    };

    events = loadJson(EVENTS_KEY, []);
    viewDate = startOfMonth(new Date());
    selectedDate = localDateString(new Date());

    document.querySelector("#agenda-prev").addEventListener("click", () => moveMonth(-1));
    document.querySelector("#agenda-next").addEventListener("click", () => moveMonth(1));
    document.querySelector("#agenda-mini-prev").addEventListener("click", () => moveMonth(-1));
    document.querySelector("#agenda-mini-next").addEventListener("click", () => moveMonth(1));
    document.querySelector("#agenda-today").addEventListener("click", goToday);
    document.querySelector("#agenda-new-event").addEventListener("click", () => openEventForm({ date: localDateString(new Date()) }));
    form.addEventListener("submit", saveEventFromForm);
    deleteButton.addEventListener("click", deleteCurrentEvent);
    mapsButton.addEventListener("click", openCurrentLocationInMaps);
    fields.location.addEventListener("input", updateMapsButton);
    grid.addEventListener("click", handleAgendaClick);
    miniGrid.addEventListener("click", handleMiniCalendarClick);

    renderAgenda();
  }

  function renderAgenda() {
    monthTitle.textContent = new Intl.DateTimeFormat("es-EC", {
      month: "long",
      year: "numeric"
    }).format(viewDate);
    miniTitle.textContent = monthTitle.textContent;

    grid.innerHTML = buildMonthDays(viewDate).map(dayTemplate).join("");
    miniGrid.innerHTML = buildMonthDays(viewDate).map(miniDayTemplate).join("");
    updateMonthSummary();
  }

  function dayTemplate(day) {
    const dayEvents = events
      .filter((event) => event.date === day.date)
      .sort(compareEvents);
    const eventCountLabel = dayEvents.length ? `${dayEvents.length} evento${dayEvents.length === 1 ? "" : "s"}` : "";

    return `
      <section class="agenda-day ${day.currentMonth ? "" : "outside-month"} ${day.today ? "today" : ""} ${dayEvents.length ? "has-events" : ""}" data-date="${day.date}">
        <div class="agenda-day-head">
          <span class="agenda-day-number">${day.number}</span>
          <span class="agenda-day-count">${eventCountLabel}</span>
          <button class="agenda-day-add" type="button" data-action="new" data-date="${day.date}" aria-label="Nuevo evento para ${day.date}">
            <span class="font-icon">&#xE710;</span>
          </button>
        </div>
        <div class="agenda-events">
          ${dayEvents.map(eventTemplate).join("")}
        </div>
      </section>
    `;
  }

  function miniDayTemplate(day) {
    const hasEvents = events.some((event) => event.date === day.date);
    return `
      <button class="mini-day ${day.currentMonth ? "" : "outside-month"} ${day.today ? "today" : ""} ${hasEvents ? "has-events" : ""} ${day.date === selectedDate ? "selected" : ""}" type="button" data-date="${day.date}">
        ${day.number}
      </button>
    `;
  }

  function eventTemplate(event) {
    return `
      <button class="agenda-event ${eventClass(event)}" type="button" data-action="edit" data-id="${event.id}">
        <strong>${escapeHtml(event.title)}</strong>
        <span>${escapeHtml(eventMeta(event))}</span>
      </button>
    `;
  }

  function openEventForm(event) {
    form.reset();
    const isExisting = Boolean(event.id);
    dialogTitle.textContent = isExisting ? "Editar evento" : "Nuevo evento";
    fields.id.value = isExisting ? event.id : crypto.randomUUID();
    fields.title.value = event.title || "";
    fields.date.value = event.date || localDateString(new Date());
    fields.startTime.value = event.startTime || event.time || "";
    fields.endTime.value = event.endTime || "";
    fields.category.value = normalizeCategory(event.category);
    fields.status.value = event.status || "Programado";
    fields.location.value = event.location || "";
    fields.notes.value = event.notes || "";
    deleteButton.hidden = !isExisting;
    updateMapsButton();
    dialog.showModal();
    fields.title.focus();
  }

  function saveEventFromForm(event) {
    event.preventDefault();
    const record = readEventForm();
    const index = events.findIndex((item) => item.id === record.id);

    if (index >= 0) {
      events[index] = record;
    } else {
      events.push(record);
    }

    viewDate = startOfMonth(parseLocalDate(record.date));
    selectedDate = record.date;
    saveEvents();
    renderAgenda();
    dialog.close();
  }

  function readEventForm() {
    return {
      id: fields.id.value,
      title: fields.title.value.trim(),
      date: fields.date.value,
      startTime: fields.startTime.value,
      endTime: fields.endTime.value,
      category: fields.category.value,
      status: fields.status.value,
      location: fields.location.value.trim(),
      notes: fields.notes.value.trim(),
      updatedAt: new Date().toISOString()
    };
  }

  function handleAgendaClick(event) {
    const button = event.target.closest("button");
    if (!button) return;

    if (button.dataset.action === "new") {
      selectedDate = button.dataset.date;
      openEventForm({ date: button.dataset.date });
      return;
    }

    if (button.dataset.action === "edit") {
      const record = events.find((item) => item.id === button.dataset.id);
      if (record) openEventForm(record);
    }
  }

  function moveMonth(offset) {
    viewDate = new Date(viewDate.getFullYear(), viewDate.getMonth() + offset, 1);
    selectedDate = localDateString(viewDate);
    renderAgenda();
  }

  function goToday() {
    viewDate = startOfMonth(new Date());
    selectedDate = localDateString(new Date());
    renderAgenda();
  }

  function handleMiniCalendarClick(event) {
    const button = event.target.closest("[data-date]");
    if (!button) return;

    selectedDate = button.dataset.date;
    viewDate = startOfMonth(parseLocalDate(selectedDate));
    renderAgenda();
  }

  function buildMonthDays(date) {
    const monthStart = startOfMonth(date);
    const gridStart = new Date(monthStart);
    const mondayOffset = (monthStart.getDay() + 6) % 7;
    gridStart.setDate(monthStart.getDate() - mondayOffset);

    return Array.from({ length: 42 }, (_, index) => {
      const current = new Date(gridStart);
      current.setDate(gridStart.getDate() + index);
      return {
        date: localDateString(current),
        number: current.getDate(),
        currentMonth: current.getMonth() === monthStart.getMonth(),
        today: localDateString(current) === localDateString(new Date())
      };
    });
  }

  function compareEvents(a, b) {
    return String(eventStartTime(a) || "99:99").localeCompare(String(eventStartTime(b) || "99:99")) ||
      String(a.title).localeCompare(String(b.title));
  }

  function eventMeta(event) {
    const parts = [];
    const range = eventTimeRange(event);
    if (range) parts.push(range);
    parts.push(event.category || "Reunion");
    if (event.location) parts.push(event.location);
    if (event.status && event.status !== "Programado") parts.push(event.status);
    return parts.join(" - ");
  }

  function eventClass(event) {
    const category = normalizeClassName(event.category || "Reunion");
    const status = normalizeClassName(event.status || "");
    return `${category} ${status}`;
  }

  function normalizeCategory(value) {
    return CATEGORIES.includes(value) ? value : CATEGORIES[0];
  }

  function normalizeClassName(value) {
    return String(value)
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/\s+/g, "-");
  }

  function eventStartTime(event) {
    return event.startTime || event.time || "";
  }

  function eventTimeRange(event) {
    const start = eventStartTime(event);
    const end = event.endTime || "";
    if (start && end) return `${start} - ${end}`;
    return start || end;
  }

  function saveEvents() {
    saveJson(EVENTS_KEY, events);
  }

  function updateMonthSummary() {
    const month = viewDate.getMonth();
    const year = viewDate.getFullYear();
    const monthEvents = events.filter((event) => {
      const date = parseLocalDate(event.date);
      return date.getMonth() === month && date.getFullYear() === year;
    });

    document.querySelector("#agenda-summary-total").textContent = monthEvents.length;
    document.querySelector("#agenda-summary-meetings").textContent = monthEvents.filter((event) => event.category === "Reunion").length;
    document.querySelector("#agenda-summary-location").textContent = monthEvents.filter((event) => event.location).length;
  }

  function updateMapsButton() {
    mapsButton.hidden = fields.location.value.trim() === "";
  }

  function openCurrentLocationInMaps() {
    const location = fields.location.value.trim();
    if (!location) return;

    const url = /^https?:\/\//i.test(location)
      ? location
      : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(location)}`;
    window.open(url, "_blank", "noopener");
  }

  function deleteCurrentEvent() {
    const id = fields.id.value;
    const record = events.find((item) => item.id === id);
    if (!record) return;

    const confirmed = confirm("Eliminar este evento?");
    if (!confirmed) return;

    events = events.filter((item) => item.id !== id);
    saveEvents();
    renderAgenda();
    dialog.close();
  }

  function startOfMonth(date) {
    return new Date(date.getFullYear(), date.getMonth(), 1);
  }

  function parseLocalDate(value) {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day);
  }

  function localDateString(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  window.NotasAgenda = {
    initAgenda
  };
})();

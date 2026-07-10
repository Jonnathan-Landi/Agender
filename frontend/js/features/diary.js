(function () {
  const TASKS_KEY = "agender.diary.tasks";
  const FOCUS_KEY = "agender.diary.focus";
  const CATEGORIES = [
    "Desarrollo y Programacion",
    "Procesamiento de Datos",
    "Gestion Documental",
    "Contratacion Publica",
    "Proyectos Institucionales",
    "Solicitudes de Informacion"
  ];
  const { loadJson, saveJson } = window.NotasStorage;
  const { escapeHtml, formatDate } = window.NotasUtils;

  let tasks = [];
  let focusNotes = {};
  let fields;
  let selectedDate;
  let statusFilter;
  let searchInput;
  let taskList;
  let emptyState;
  let dialog;
  let form;
  let dialogTitle;
  let focusNote;

  function initDiary() {
    selectedDate = document.querySelector("#diary-date");
    statusFilter = document.querySelector("#diary-status-filter");
    searchInput = document.querySelector("#diary-search");
    taskList = document.querySelector("#diary-task-list");
    emptyState = document.querySelector("#diary-empty-state");
    dialog = document.querySelector("#diary-task-dialog");
    form = document.querySelector("#diary-task-form");
    dialogTitle = document.querySelector("#diary-dialog-title");
    focusNote = document.querySelector("#diary-focus-note");

    fields = {
      id: document.querySelector("#diary-task-id"),
      title: document.querySelector("#diary-task-title"),
      date: document.querySelector("#diary-task-date"),
      dueDate: document.querySelector("#diary-task-due-date"),
      category: document.querySelector("#diary-task-category"),
      priority: document.querySelector("#diary-task-priority"),
      status: document.querySelector("#diary-task-status"),
      progress: document.querySelector("#diary-task-progress"),
      notes: document.querySelector("#diary-task-notes")
    };

    tasks = loadJson(TASKS_KEY, []);
    focusNotes = loadJson(FOCUS_KEY, {});
    selectedDate.value = today();

    document.querySelector("#diary-new-task").addEventListener("click", () => openTaskForm());
    document.querySelector("#diary-today").addEventListener("click", goToday);
    const filterMenu = document.querySelector("#diary-filter-menu");
    const filterToggle = document.querySelector("#diary-filter-toggle");
    window.NotasUI.initDismissibleMenu({ menu: filterMenu, toggle: filterToggle });
    selectedDate.addEventListener("change", handleDateChange);
    statusFilter.addEventListener("change", renderDiary);
    searchInput.addEventListener("input", renderDiary);
    focusNote.addEventListener("input", saveFocusNote);
    form.addEventListener("submit", saveTaskFromForm);
    fields.status.addEventListener("change", syncProgressWithStatus);
    taskList.addEventListener("click", handleTaskAction);
    taskList.addEventListener("change", handleTaskChange);

    renderDiary();
  }

  function openTaskForm(task) {
    form.reset();
    dialogTitle.textContent = task ? "Editar tarea" : "Nueva tarea";
    fields.id.value = task ? task.id : crypto.randomUUID();
    fields.title.value = task ? task.title : "";
    fields.date.value = task ? task.date : selectedDate.value || today();
    fields.dueDate.value = task ? task.dueDate || "" : "";
    fields.category.value = task ? normalizeCategory(task.category) : CATEGORIES[0];
    fields.priority.value = task ? task.priority : "Media";
    fields.status.value = task ? task.status : "Pendiente";
    fields.progress.value = task ? task.progress : 0;
    fields.notes.value = task ? task.notes : "";
    dialog.showModal();
    fields.title.focus();
  }

  function openTaskById(id) {
    const task = tasks.find((item) => item.id === id);
    if (task) openTaskForm(task);
  }

  function saveTaskFromForm(event) {
    event.preventDefault();
    const task = readTaskForm();
    const existingIndex = tasks.findIndex((item) => item.id === task.id);

    if (existingIndex >= 0) {
      tasks[existingIndex] = task;
    } else {
      tasks.unshift(task);
    }

    saveTasks();
    notifyDiaryChanged();
    selectedDate.value = task.date;
    renderDiary();
    dialog.close();
  }

  function readTaskForm() {
    const progress = clampProgress(Number(fields.progress.value));
    return {
      id: fields.id.value,
      title: fields.title.value.trim(),
      date: fields.date.value,
      dueDate: fields.dueDate.value,
      category: fields.category.value,
      priority: fields.priority.value,
      status: fields.status.value,
      progress: fields.status.value === "Finalizada" ? 100 : progress,
      notes: fields.notes.value.trim(),
      updatedAt: new Date().toISOString()
    };
  }

  function handleTaskAction(event) {
    const button = event.target.closest("button");
    if (!button) return;

    const task = tasks.find((item) => item.id === button.dataset.id);
    if (!task) return;

    if (button.dataset.action === "edit") {
      openTaskForm(task);
    }

    if (button.dataset.action === "delete") {
      const confirmed = confirm("Eliminar esta tarea?");
      if (!confirmed) return;
      tasks = tasks.filter((item) => item.id !== task.id);
      saveTasks();
      notifyDiaryChanged();
      renderDiary();
    }
  }

  function handleTaskChange(event) {
    const select = event.target.closest("[data-diary-status]");
    if (!select) return;

    const task = tasks.find((item) => item.id === select.dataset.id);
    if (!task) return;

    task.status = select.value;
    task.progress = statusProgress(select.value, task.progress);
    task.updatedAt = new Date().toISOString();
    saveTasks();
    notifyDiaryChanged();
    renderDiary();
  }

  function renderDiary() {
    const date = selectedDate.value || today();
    const visibleTasks = getVisibleTasks(date);

    focusNote.value = focusNotes[date] || "";
    document.querySelector("#diary-list-title").textContent = formatDate(date);
    document.querySelector("#diary-list-count").textContent = `${visibleTasks.length} ${visibleTasks.length === 1 ? "tarea" : "tareas"}`;
    taskList.innerHTML = visibleTasks.map(taskTemplate).join("");
    emptyState.classList.toggle("visible", visibleTasks.length === 0);
    updateAllTaskCounts();
  }

  function updateAllTaskCounts() {
    const counts = tasks.reduce((result, task) => {
      result[task.status] = (result[task.status] || 0) + 1;
      return result;
    }, {});
    document.querySelector("#diary-all-pending").textContent = counts.Pendiente || 0;
    document.querySelector("#diary-all-progress").textContent = counts["En proceso"] || 0;
    document.querySelector("#diary-all-waiting").textContent = counts["En espera"] || 0;
    document.querySelector("#diary-all-done").textContent = counts.Finalizada || 0;
  }

  function getVisibleTasks(date) {
    const status = statusFilter.value;
    const query = searchInput.value.trim().toLowerCase();
    return tasks
      .filter((task) => task.date === date)
      .filter((task) => !status || task.status === status)
      .filter((task) => {
        const searchable = [task.title, task.category, task.priority, task.status, task.dueDate, task.notes].join(" ").toLowerCase();
        return !query || searchable.includes(query);
      })
      .sort(compareTasks);
  }

  function taskTemplate(task) {
    const deadline = deadlineInfo(task);
    return `
      <article class="diary-task ${statusClass(task.status)} ${deadline.className}">
        <div class="diary-task-main">
          <div class="diary-task-topline">
            <span class="diary-priority ${priorityClass(task.priority)}">${escapeHtml(task.priority)}</span>
            <span>${escapeHtml(dueDateLabel(task.dueDate))}</span>
            ${deadline.label ? `<span class="diary-deadline-alert"><span class="font-icon" aria-hidden="true">&#xE7BA;</span>${escapeHtml(deadline.label)}</span>` : ""}
            <span>${escapeHtml(task.category || "General")}</span>
          </div>
          <h2>${escapeHtml(task.title)}</h2>
          ${task.notes ? `<p>${escapeHtml(task.notes)}</p>` : ""}
          <div class="diary-progress-track" aria-label="Avance ${task.progress}%">
            <span style="width: ${clampProgress(task.progress)}%"></span>
          </div>
        </div>
        <div class="diary-task-controls">
          <select data-diary-status data-id="${task.id}" aria-label="Estado de ${escapeHtml(task.title)}">
            ${["Pendiente", "En proceso", "En espera", "Finalizada"].map((status) => `
              <option ${task.status === status ? "selected" : ""}>${status}</option>
            `).join("")}
          </select>
          <strong>${clampProgress(task.progress)}%</strong>
          <div class="row-actions">
            <button type="button" data-action="edit" data-id="${task.id}">Editar</button>
            <button class="danger" type="button" data-action="delete" data-id="${task.id}">Borrar</button>
          </div>
        </div>
      </article>
    `;
  }

  function handleDateChange() {
    renderDiary();
  }

  function goToday() {
    selectedDate.value = today();
    renderDiary();
  }

  function saveFocusNote() {
    const date = selectedDate.value || today();
    focusNotes[date] = focusNote.value.trim();
    saveJson(FOCUS_KEY, focusNotes);
  }

  function saveTasks() {
    saveJson(TASKS_KEY, tasks);
  }

  function notifyDiaryChanged() {
    window.dispatchEvent(new CustomEvent("agender:diary-changed"));
  }

  function deadlineInfo(task) {
    if (!task.dueDate || task.status === "Finalizada") return { label: "", className: "" };
    const due = parseDateOnly(task.dueDate);
    const current = parseDateOnly(today());
    const days = Math.round((due - current) / 86400000);
    if (days < 0) return { label: `Vencida hace ${Math.abs(days)} ${Math.abs(days) === 1 ? "día" : "días"}`, className: "deadline-overdue" };
    if (days === 0) return { label: "Vence hoy", className: "deadline-today" };
    if (days <= 3) return { label: `Vence en ${days} ${days === 1 ? "día" : "días"}`, className: "deadline-soon" };
    return { label: "", className: "" };
  }

  function parseDateOnly(value) {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day);
  }

  function syncProgressWithStatus() {
    fields.progress.value = statusProgress(fields.status.value, Number(fields.progress.value));
  }

  function statusProgress(status, currentProgress) {
    if (status === "Finalizada") return 100;
    if (status === "Pendiente" && currentProgress === 100) return 0;
    if (status === "En proceso" && currentProgress === 0) return 25;
    if (status === "En espera" && currentProgress === 100) return 50;
    return clampProgress(currentProgress);
  }

  function compareTasks(a, b) {
    const statusOrder = { "En proceso": 0, Pendiente: 1, "En espera": 2, Finalizada: 3 };
    const priorityOrder = { Alta: 0, Media: 1, Baja: 2 };
    return (statusOrder[a.status] ?? 9) - (statusOrder[b.status] ?? 9) ||
      (priorityOrder[a.priority] ?? 9) - (priorityOrder[b.priority] ?? 9) ||
      String(a.dueDate || "9999-12-31").localeCompare(String(b.dueDate || "9999-12-31"));
  }

  function clampProgress(value) {
    if (!Number.isFinite(value)) return 0;
    return Math.min(100, Math.max(0, Math.round(value)));
  }

  function priorityClass(priority) {
    return `priority-${priority.toLowerCase()}`;
  }

  function statusClass(status) {
    const normalized = status.toLowerCase().replace(/\s+/g, "-");
    return `task-${normalized}`;
  }

  function dueDateLabel(value) {
    return value ? `Final: ${formatDate(value)}` : "Sin fecha final";
  }

  function normalizeCategory(value) {
    return CATEGORIES.includes(value) ? value : CATEGORIES[0];
  }

  function today() {
    const date = new Date();
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  window.NotasDiary = {
    initDiary,
    openTaskById
  };
})();

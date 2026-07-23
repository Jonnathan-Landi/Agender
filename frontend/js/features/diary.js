(function () {
  const TASKS_KEY = "agender.diary.tasks";
  const CATEGORIES = [
    "Desarrollo y Programacion",
    "Procesamiento de Datos",
    "Gestion Documental",
    "Contratacion Publica",
    "Proyectos Institucionales",
    "Solicitudes de Informacion"
  ];
  const STATUSES = ["Pendiente", "En proceso", "En espera", "Finalizada"];
  const BOARD_RETENTION_MS = 2 * 24 * 60 * 60 * 1000;
  const { loadJson, saveJson } = window.NotasStorage;
  const { escapeHtml, formatDate } = window.NotasUtils;

  let tasks = [];
  let fields;
  let selectedDate;
  let statusFilter;
  let searchInput;
  let taskList;
  let emptyState;
  let dialog;
  let form;
  let dialogTitle;
  let statusBoard;
  let boardContextMenu;
  let boardContextTaskId = "";
  let deleteTaskId = "";
  let deleteDialog;
  let deleteForm;
  let deleteMessage;
  let activeDiaryView = "plan";
  let pointerDrag = null;
  let suppressBoardClick = false;

  function initDiary() {
    selectedDate = document.querySelector("#diary-date");
    statusFilter = document.querySelector("#diary-status-filter");
    searchInput = document.querySelector("#diary-search");
    taskList = document.querySelector("#diary-task-list");
    emptyState = document.querySelector("#diary-empty-state");
    dialog = document.querySelector("#diary-task-dialog");
    form = document.querySelector("#diary-task-form");
    dialogTitle = document.querySelector("#diary-dialog-title");
    statusBoard = document.querySelector("#diary-status-board");
    boardContextMenu = document.querySelector("#diary-board-context-menu");
    deleteDialog = document.querySelector("#diary-delete-dialog");
    deleteForm = document.querySelector("#diary-delete-form");
    deleteMessage = document.querySelector("#diary-delete-message");

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
    selectedDate.value = today();

    document.querySelector("#diary-new-task").addEventListener("click", () => openTaskForm());
    const filterMenu = document.querySelector("#diary-filter-menu");
    const filterToggle = document.querySelector("#diary-filter-toggle");
    window.NotasUI.initDismissibleMenu({ menu: filterMenu, toggle: filterToggle });
    document.querySelector("#diary-date-trigger").addEventListener("click", openDatePicker);
    selectedDate.addEventListener("change", handleDateChange);
    statusFilter.addEventListener("change", renderDiary);
    searchInput.addEventListener("input", renderDiary);
    form.addEventListener("submit", saveTaskFromForm);
    fields.status.addEventListener("change", syncProgressWithStatus);
    taskList.addEventListener("click", handleTaskAction);
    taskList.addEventListener("change", handleTaskChange);
    document.querySelector("#diary-upcoming-list").addEventListener("click", handleDeadlineListClick);
    document.querySelector("#diary-overdue-list").addEventListener("click", handleDeadlineListClick);
    document.querySelectorAll("[data-diary-view]").forEach((button) => {
      button.addEventListener("click", () => selectDiaryView(button.dataset.diaryView));
    });
    statusBoard.addEventListener("click", handleBoardClick);
    statusBoard.addEventListener("contextmenu", handleBoardContextMenu);
    statusBoard.addEventListener("pointerdown", handleBoardPointerDown);
    statusBoard.addEventListener("pointermove", handleBoardPointerMove);
    statusBoard.addEventListener("pointerup", handleBoardPointerUp);
    statusBoard.addEventListener("pointercancel", cancelBoardPointerDrag);
    boardContextMenu.addEventListener("click", handleBoardMenuAction);
    deleteForm.addEventListener("submit", confirmTaskDeletion);
    document.querySelector("#diary-delete-cancel").addEventListener("click", cancelTaskDeletion);
    deleteDialog.addEventListener("close", () => {
      if (deleteDialog.returnValue !== "deleted") deleteTaskId = "";
    });
    document.addEventListener("pointerdown", dismissBoardContextMenu);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeBoardContextMenu();
    });
    window.addEventListener("agender:data-refreshed", handleRemoteDataRefresh);

    renderDiary();
  }

  function handleRemoteDataRefresh(event) {
    const keys = event.detail?.keys || [];
    if (!keys.includes(TASKS_KEY)) return;
    if (pointerDrag) clearBoardPointerDrag();
    closeBoardContextMenu();
    tasks = loadJson(TASKS_KEY, []);
    renderDiary();
  }

  function openTaskForm(task, defaults = {}) {
    form.reset();
    dialogTitle.textContent = task ? "Editar tarea" : "Nueva tarea";
    fields.id.value = task ? task.id : crypto.randomUUID();
    fields.title.value = task ? task.title : "";
    fields.date.value = task ? task.date : defaults.date || selectedDate.value || today();
    fields.dueDate.value = task ? task.dueDate || "" : "";
    fields.category.value = task ? normalizeCategory(task.category) : CATEGORIES[0];
    fields.priority.value = task ? task.priority : "Media";
    fields.status.value = task ? task.status : defaults.status || "Pendiente";
    fields.progress.value = task ? task.progress : statusProgress(fields.status.value, 0);
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
    const existing = tasks.find((item) => item.id === fields.id.value);
    const status = fields.status.value;
    return {
      id: fields.id.value,
      title: fields.title.value.trim(),
      date: fields.date.value,
      dueDate: fields.dueDate.value,
      category: fields.category.value,
      priority: fields.priority.value,
      status,
      progress: status === "Finalizada" ? 100 : progress,
      notes: fields.notes.value.trim(),
      updatedAt: new Date().toISOString(),
      statusChangedAt: existing?.status === status && existing.statusChangedAt
        ? existing.statusChangedAt
        : new Date().toISOString()
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
      requestTaskDeletion(task);
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
    task.statusChangedAt = task.updatedAt;
    saveTasks();
    notifyDiaryChanged();
    renderDiary();
  }

  function renderDiary() {
    const date = selectedDate.value || today();
    const visibleTasks = getVisibleTasks(date);

    document.querySelector("#diary-list-title").textContent = formatDate(date);
    document.querySelector("#diary-list-count").textContent = `${visibleTasks.length} ${visibleTasks.length === 1 ? "tarea" : "tareas"}`;
    taskList.innerHTML = visibleTasks.map(taskTemplate).join("");
    emptyState.classList.toggle("visible", visibleTasks.length === 0);
    updateDaySummary(date);
    renderUpcomingTasks();
    renderOverdueTasks();
    renderStatusBoard();
  }

  function handleDeadlineListClick(event) {
    const button = event.target.closest("[data-deadline-task]");
    if (button) openTaskById(button.dataset.deadlineTask);
  }

  function updateDaySummary(date) {
    const dayTasks = tasks.filter((task) => task.date === date);
    const counts = dayTasks.reduce((result, task) => {
      result[task.status] = (result[task.status] || 0) + 1;
      return result;
    }, {});
    document.querySelector("#diary-chart-total").textContent = dayTasks.length;
    renderStatusChart(counts, dayTasks.length);
  }

  function renderStatusChart(counts, total) {
    const values = STATUSES.map((status) => counts[status] || 0);
    const colors = ["#ff5f57", "#1683f8", "#ffb900", "#39b75d"];
    let offset = 0;
    const stops = values.map((value, index) => {
      const start = offset;
      offset += total ? value / total * 100 : 0;
      return `${colors[index]} ${start}% ${offset}%`;
    });
    document.querySelector("#diary-status-chart").style.background = total
      ? `conic-gradient(${stops.join(", ")})`
      : "var(--line)";
    document.querySelector("#diary-chart-legend").innerHTML = STATUSES.map((status, index) => {
      const count = values[index];
      const percent = total ? Math.round(count / total * 100) : 0;
      return `<div><i style="background:${colors[index]}"></i><span>${escapeHtml(status)}</span><strong>${count} (${percent}%)</strong></div>`;
    }).join("");
  }

  function renderUpcomingTasks() {
    const upcoming = tasks
      .filter((task) => task.status !== "Finalizada" && task.dueDate && task.dueDate >= today())
      .sort((left, right) => left.dueDate.localeCompare(right.dueDate));
    renderDeadlineList("#diary-upcoming-list", "#diary-upcoming-count", upcoming, "No hay tareas próximas a vencer.", false);
  }

  function getOverdueTasks() {
    return tasks
      .filter((task) => task.status !== "Finalizada" && task.dueDate && task.dueDate < today())
      .sort((left, right) => left.dueDate.localeCompare(right.dueDate));
  }

  function renderOverdueTasks() {
    const overdue = getOverdueTasks();
    renderDeadlineList("#diary-overdue-list", "#diary-overdue-count", overdue, "No hay tareas vencidas.", true);
  }

  function renderDeadlineList(listSelector, countSelector, deadlineTasks, emptyMessage, overdue) {
    document.querySelector(countSelector).textContent = deadlineTasks.length;
    document.querySelector(listSelector).innerHTML = deadlineTasks.length
      ? deadlineTasks.map((task) => deadlineTaskTemplate(task, overdue)).join("")
      : `<p>${escapeHtml(emptyMessage)}</p>`;
  }

  function deadlineTaskTemplate(task, overdue) {
    const dateLabel = `${overdue ? "Venció" : "Vence"}: ${formatDate(task.dueDate)}`;
    return `
      <button class="diary-deadline-item${overdue ? " overdue" : ""}" type="button" data-deadline-task="${escapeHtml(task.id)}">
        <span class="diary-deadline-title"><i></i><strong>${escapeHtml(task.title)}</strong></span>
        <small><span class="font-icon" aria-hidden="true">&#xE787;</span>${escapeHtml(dateLabel)}</small>
      </button>
    `;
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
    const progress = clampProgress(task.progress);
    return `
      <article class="diary-task ${statusClass(task.status)} ${deadline.className}">
        <div class="diary-task-main">
          <h2>${escapeHtml(task.title)}</h2>
          ${task.notes ? `<p>${escapeHtml(task.notes)}</p>` : ""}
        </div>
        <div class="diary-task-category"><span class="font-icon" aria-hidden="true">&#xE8B7;</span><span>${escapeHtml(task.category || "General")}</span></div>
        <div class="diary-task-due">
          <span class="font-icon" aria-hidden="true">${deadline.label ? "&#xE7BA;" : "&#xE787;"}</span>
          <span>${deadline.label ? escapeHtml(deadline.label) : escapeHtml(dueDateLabel(task.dueDate))}</span>
        </div>
        <div class="diary-task-status">
          <select data-diary-status data-id="${task.id}" aria-label="Estado de ${escapeHtml(task.title)}">
            ${STATUSES.map((status) => `
              <option ${task.status === status ? "selected" : ""}>${status}</option>
            `).join("")}
          </select>
        </div>
        <div class="diary-task-progress"><strong>${progress}%</strong><div class="diary-progress-track" aria-label="Avance ${progress}%"><span style="width: ${progress}%"></span></div></div>
        <div class="diary-task-actions">
          <button type="button" data-action="edit" data-id="${task.id}" aria-label="Editar ${escapeHtml(task.title)}"><span class="font-icon" aria-hidden="true">&#xE70F;</span></button>
          <button class="danger" type="button" data-action="delete" data-id="${task.id}" aria-label="Borrar ${escapeHtml(task.title)}"><span class="font-icon" aria-hidden="true">&#xE74D;</span></button>
        </div>
      </article>
    `;
  }

  function handleDateChange() {
    renderDiary();
  }

  function openDatePicker() {
    selectedDate.focus({ preventScroll: true });
    if (typeof selectedDate.showPicker === "function") {
      try {
        selectedDate.showPicker();
        return;
      } catch (_error) {
        // WebViews antiguos continúan con el clic nativo.
      }
    }
    selectedDate.click();
  }

  function selectDiaryView(view) {
    activeDiaryView = view === "board" ? "board" : "plan";
    document.querySelectorAll("[data-diary-view]").forEach((button) => {
      const active = button.dataset.diaryView === activeDiaryView;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
    });
    document.querySelector("#diary-plan-view").classList.toggle("active", activeDiaryView === "plan");
    document.querySelector("#diary-board-view").classList.toggle("active", activeDiaryView === "board");
    if (activeDiaryView === "board") renderStatusBoard();
  }

  function renderStatusBoard() {
    const query = searchInput.value.trim().toLowerCase();
    const visibleTasks = tasks.filter((task) => {
      const searchable = [task.title, task.category, task.priority, task.status, task.dueDate, task.notes]
        .join(" ")
        .toLowerCase();
      return (!query || searchable.includes(query)) && !isExpiredBoardTask(task);
    });
    statusBoard.innerHTML = STATUSES.map((status) => {
      const columnTasks = visibleTasks.filter((task) => task.status === status);
      return boardColumnTemplate(status, columnTasks);
    }).join("");
  }

  function boardColumnTemplate(status, columnTasks) {
    return `
      <section class="diary-board-column ${statusClass(status)}" data-board-status="${escapeHtml(status)}">
        <header>
          <div><i aria-hidden="true"></i><strong>${escapeHtml(status)}</strong><span>${columnTasks.length}</span></div>
        </header>
        <div class="diary-board-cards">
          ${columnTasks.map(boardCardTemplate).join("")}
          ${columnTasks.length ? "" : '<p class="diary-board-empty">Sin tareas en este estado</p>'}
        </div>
        <button class="diary-board-add" type="button" data-board-action="add" data-status="${escapeHtml(status)}">
          <span class="font-icon" aria-hidden="true">&#xE710;</span><span>Agregar tarea</span>
        </button>
      </section>
    `;
  }

  function boardCardTemplate(task) {
    const deadline = deadlineInfo(task);
    return `
      <article class="diary-board-card ${deadline.className}" data-task-id="${task.id}" tabindex="0">
        <div class="diary-board-card-meta">
          <div class="diary-board-priority-control">
            <button class="diary-priority diary-board-priority ${priorityClass(task.priority)}" type="button"
              data-board-priority-toggle="${task.id}" aria-haspopup="menu" aria-expanded="false">
              <span>${escapeHtml(task.priority)}</span><span class="font-icon" aria-hidden="true">&#xE70D;</span>
            </button>
            <div class="diary-board-priority-menu" role="menu" hidden>
              ${["Alta", "Media", "Baja"].map((priority) => `
                <button type="button" role="menuitemradio" aria-checked="${task.priority === priority}"
                  data-board-priority-value="${escapeHtml(priority)}" data-task-id="${task.id}">
                  <i class="${priorityClass(priority)}" aria-hidden="true"></i><span>${priority}</span>
                </button>
              `).join("")}
            </div>
          </div>
          <span>${escapeHtml(task.category || "General")}</span>
        </div>
        <h2>${escapeHtml(task.title)}</h2>
        ${task.notes ? `<p>${escapeHtml(task.notes)}</p>` : ""}
        <footer>
          <span>${escapeHtml(dueDateLabel(task.dueDate))}</span>
          <strong>${clampProgress(task.progress)}%</strong>
        </footer>
      </article>
    `;
  }

  function handleBoardClick(event) {
    if (suppressBoardClick) {
      event.preventDefault();
      return;
    }
    const addButton = event.target.closest('[data-board-action="add"]');
    if (addButton) {
      openTaskForm(null, { status: addButton.dataset.status });
      return;
    }
    const priorityToggle = event.target.closest("[data-board-priority-toggle]");
    if (priorityToggle) {
      const menu = priorityToggle.nextElementSibling;
      const opening = menu.hidden;
      closeBoardPriorityMenus();
      menu.hidden = !opening;
      priorityToggle.setAttribute("aria-expanded", String(opening));
      return;
    }
    const priorityOption = event.target.closest("[data-board-priority-value]");
    if (priorityOption) {
      updateBoardPriority(priorityOption.dataset.taskId, priorityOption.dataset.boardPriorityValue);
    }
  }

  function updateBoardPriority(taskId, value) {
    const task = tasks.find((item) => item.id === taskId);
    if (!task || task.priority === value) {
      closeBoardPriorityMenus();
      return;
    }
    task.priority = value;
    task.updatedAt = new Date().toISOString();
    saveTasks();
    notifyDiaryChanged();
    renderDiary();
  }

  function handleBoardPointerDown(event) {
    if (event.button !== 0) return;
    if (event.target.closest("button, input, textarea, a")) return;
    const card = event.target.closest("[data-task-id]");
    if (!card) return;
    pointerDrag = {
      card,
      id: card.dataset.taskId,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      offsetX: event.clientX - card.getBoundingClientRect().left,
      offsetY: event.clientY - card.getBoundingClientRect().top,
      moved: false,
      target: null,
      ghost: null,
      placeholder: null
    };
    card.setPointerCapture(event.pointerId);
  }

  function handleBoardPointerMove(event) {
    if (!pointerDrag || pointerDrag.pointerId !== event.pointerId) return;
    const distance = Math.hypot(event.clientX - pointerDrag.startX, event.clientY - pointerDrag.startY);
    if (!pointerDrag.moved && distance < 6) return;
    if (!pointerDrag.moved) {
      pointerDrag.moved = true;
      pointerDrag.card.classList.add("dragging");
      document.body.classList.add("diary-card-dragging");
      pointerDrag.ghost = createBoardDragGhost(pointerDrag);
      pointerDrag.placeholder = document.createElement("div");
      pointerDrag.placeholder.className = "diary-board-drop-placeholder";
    }
    event.preventDefault();
    positionBoardDragGhost(pointerDrag, event.clientX, event.clientY);
    const column = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-board-status]");
    statusBoard.querySelectorAll(".drag-over").forEach((item) => item.classList.remove("drag-over"));
    pointerDrag.target = column && statusBoard.contains(column) ? column : null;
    if (pointerDrag.target) {
      pointerDrag.target.classList.add("drag-over");
      pointerDrag.target.querySelector(".diary-board-cards")?.append(pointerDrag.placeholder);
    } else {
      pointerDrag.placeholder.remove();
    }
  }

  function handleBoardPointerUp(event) {
    if (!pointerDrag || pointerDrag.pointerId !== event.pointerId) return;
    const { card, id, moved, target } = pointerDrag;
    if (card.hasPointerCapture(event.pointerId)) card.releasePointerCapture(event.pointerId);
    if (moved) {
      suppressBoardClick = true;
      setTimeout(() => { suppressBoardClick = false; }, 0);
    }
    const task = tasks.find((item) => item.id === id);
    if (moved && target && task && task.status !== target.dataset.boardStatus) {
      task.status = target.dataset.boardStatus;
      task.progress = statusProgress(task.status, task.progress);
      task.updatedAt = new Date().toISOString();
      task.statusChangedAt = task.updatedAt;
      saveTasks();
      notifyDiaryChanged();
      renderDiary();
    }
    clearBoardPointerDrag();
  }

  function cancelBoardPointerDrag(event) {
    if (!pointerDrag || pointerDrag.pointerId !== event.pointerId) return;
    clearBoardPointerDrag();
  }

  function clearBoardPointerDrag() {
    pointerDrag?.ghost?.remove();
    pointerDrag?.placeholder?.remove();
    pointerDrag = null;
    document.body.classList.remove("diary-card-dragging");
    statusBoard.querySelectorAll(".dragging, .drag-over").forEach((item) => {
      item.classList.remove("dragging", "drag-over");
    });
  }

  function createBoardDragGhost(drag) {
    const ghost = drag.card.cloneNode(true);
    const bounds = drag.card.getBoundingClientRect();
    ghost.className = "diary-board-drag-ghost";
    ghost.removeAttribute("data-task-id");
    ghost.removeAttribute("tabindex");
    ghost.style.width = `${bounds.width}px`;
    document.body.append(ghost);
    return ghost;
  }

  function positionBoardDragGhost(drag, clientX, clientY) {
    drag.ghost.style.left = `${clientX - drag.offsetX}px`;
    drag.ghost.style.top = `${clientY - drag.offsetY}px`;
  }

  function handleBoardContextMenu(event) {
    const card = event.target.closest("[data-task-id]");
    if (!card) return;
    event.preventDefault();
    boardContextTaskId = card.dataset.taskId;
    boardContextMenu.hidden = false;
    const bounds = boardContextMenu.getBoundingClientRect();
    boardContextMenu.style.left = `${Math.min(event.clientX, window.innerWidth - bounds.width - 8)}px`;
    boardContextMenu.style.top = `${Math.min(event.clientY, window.innerHeight - bounds.height - 8)}px`;
    boardContextMenu.querySelector("button")?.focus();
  }

  function handleBoardMenuAction(event) {
    const button = event.target.closest("[data-board-menu-action]");
    if (!button) return;
    const task = tasks.find((item) => item.id === boardContextTaskId);
    closeBoardContextMenu();
    if (!task) return;
    if (button.dataset.boardMenuAction === "edit") {
      openTaskForm(task);
      return;
    }
    if (button.dataset.boardMenuAction === "delete") {
      requestTaskDeletion(task);
    }
  }

  function requestTaskDeletion(task) {
    deleteTaskId = task.id;
    deleteMessage.textContent = `Se eliminará “${task.title}”. Esta acción no se puede deshacer.`;
    deleteDialog.returnValue = "";
    deleteDialog.showModal();
  }

  function confirmTaskDeletion(event) {
    event.preventDefault();
    if (!deleteTaskId) {
      deleteDialog.close();
      return;
    }
    tasks = tasks.filter((item) => item.id !== deleteTaskId);
    deleteTaskId = "";
    saveTasks();
    notifyDiaryChanged();
    renderDiary();
    deleteDialog.close("deleted");
  }

  function cancelTaskDeletion() {
    deleteTaskId = "";
    deleteDialog.close();
  }

  function dismissBoardContextMenu(event) {
    if (!boardContextMenu.hidden && !boardContextMenu.contains(event.target)) closeBoardContextMenu();
    if (!event.target.closest(".diary-board-priority-control")) closeBoardPriorityMenus();
  }

  function closeBoardContextMenu() {
    boardContextMenu.hidden = true;
    boardContextTaskId = "";
  }

  function closeBoardPriorityMenus() {
    statusBoard.querySelectorAll(".diary-board-priority-menu:not([hidden])").forEach((menu) => {
      menu.hidden = true;
      menu.previousElementSibling?.setAttribute("aria-expanded", "false");
    });
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

  function isExpiredBoardTask(task) {
    if (task.status !== "Finalizada") return false;
    const changedAt = new Date(task.statusChangedAt || task.updatedAt || "").getTime();
    return Number.isFinite(changedAt) && Date.now() - changedAt > BOARD_RETENTION_MS;
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

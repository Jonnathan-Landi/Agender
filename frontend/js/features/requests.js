(function () {
  const STORAGE_KEY = "agender.request.records";
  const STATUSES = ["Recibido", "En formalización", "Despachado por Quipux", "Entregado", "Archivado"];
  const PRIORITIES = ["Alta", "Media", "Baja"];
  const { escapeHtml } = window.NotasUtils;
  const { loadJson, saveJson } = window.NotasStorage;

  let records = [];
  let fields;
  let body;
  let dialog;
  let form;
  let dialogTitle;
  let emptyState;
  let searchInput;
  let priorityFilter;
  let statusFilter;
  let statusBoard;
  let contextMenu;
  let contextRecordId = "";
  let deleteRecordId = "";
  let pointerDrag = null;
  let suppressBoardClick = false;
  let pendingFiles = { request: [], response: [], additional: [] };

  function initRequests() {
    fields = {
      id: document.querySelector("#record-id"),
      requester: document.querySelector("#requester"),
      requestDocument: document.querySelector("#request-document"),
      requestDate: document.querySelector("#request-date"),
      requestDatePicker: document.querySelector("#request-date-picker"),
      objective: document.querySelector("#request-objective"),
      requestedInformation: document.querySelector("#requested-information"),
      status: document.querySelector("#status"),
      priority: document.querySelector("#request-priority"),
      responseDate: document.querySelector("#response-date"),
      responseDatePicker: document.querySelector("#response-date-picker"),
      responseDocument: document.querySelector("#response-document"),
      observations: document.querySelector("#request-observations"),
      requestPdf: document.querySelector("#request-pdf"),
      responsePdf: document.querySelector("#response-pdf"),
      additionalPdfs: document.querySelector("#additional-pdfs")
    };

    body = document.querySelector("#requests-body");
    dialog = document.querySelector("#request-dialog");
    form = document.querySelector("#request-form");
    dialogTitle = document.querySelector("#dialog-title");
    emptyState = document.querySelector("#empty-state");
    searchInput = document.querySelector("#search-input");
    priorityFilter = document.querySelector("#request-filter");
    statusFilter = document.querySelector("#status-filter");
    statusBoard = document.querySelector("#request-status-board");
    contextMenu = document.querySelector("#request-context-menu");
    records = loadRecords();

    document.querySelector("#new-request").addEventListener("click", () => openForm());
    document.querySelector("#export-excel").addEventListener("click", exportExcel);
    const filterMenu = document.querySelector("#request-filter-menu");
    const filterToggle = document.querySelector("#request-filter-toggle");
    window.NotasUI.initDismissibleMenu({ menu: filterMenu, toggle: filterToggle });
    searchInput.addEventListener("input", render);
    priorityFilter.addEventListener("change", render);
    statusFilter.addEventListener("change", render);
    document.querySelectorAll("[data-request-view]").forEach((button) => {
      button.addEventListener("click", () => selectRequestView(button.dataset.requestView));
    });

    form.addEventListener("submit", saveFromDialog);
    form.addEventListener("click", handleAttachmentAction);
    fields.requestPdf.addEventListener("change", () => selectPendingFiles("request", fields.requestPdf.files));
    fields.responsePdf.addEventListener("change", () => selectPendingFiles("response", fields.responsePdf.files));
    fields.additionalPdfs.addEventListener("change", () => selectPendingFiles("additional", fields.additionalPdfs.files));
    fields.requestDate.addEventListener("input", () => {
      syncDatePicker(fields.requestDate, fields.requestDatePicker);
      syncDateValidity();
    });
    fields.requestDatePicker.addEventListener("change", () => selectCalendarDate(fields.requestDatePicker, fields.requestDate));
    fields.responseDate.addEventListener("input", () => {
      syncDatePicker(fields.responseDate, fields.responseDatePicker);
      syncDateValidity();
      syncResponseDocumentRequirement();
    });
    fields.responseDatePicker.addEventListener("change", () => {
      selectCalendarDate(fields.responseDatePicker, fields.responseDate);
      syncResponseDocumentRequirement();
    });
    body.addEventListener("click", handleQuickChoice);
    body.addEventListener("click", handlePdfViewClick);
    body.addEventListener("contextmenu", handleRequestContextMenu);
    statusBoard.addEventListener("click", handleBoardClick);
    statusBoard.addEventListener("click", handleQuickChoice);
    statusBoard.addEventListener("contextmenu", handleRequestContextMenu);
    statusBoard.addEventListener("pointerdown", handleBoardPointerDown);
    statusBoard.addEventListener("pointermove", handleBoardPointerMove);
    statusBoard.addEventListener("pointerup", handleBoardPointerUp);
    statusBoard.addEventListener("pointercancel", cancelBoardPointerDrag);
    contextMenu.addEventListener("click", handleContextMenuAction);
    document.querySelector("#request-delete-form").addEventListener("submit", confirmRecordDeletion);
    document.querySelector("#request-delete-cancel").addEventListener("click", cancelRecordDeletion);
    document.querySelector("#request-pdf-close").addEventListener("click", closePdfViewer);
    document.addEventListener("pointerdown", dismissContextMenu);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeContextMenu();
    });
    window.addEventListener("agender:data-refreshed", handleRemoteDataRefresh);

    render();
  }

  function handleRemoteDataRefresh(event) {
    if (!event.detail?.keys?.includes(STORAGE_KEY)) return;
    if (pointerDrag) clearBoardPointerDrag();
    closeContextMenu();
    records = loadRecords();
    render();
  }

  function saveRecords() {
    return saveJson(STORAGE_KEY, records);
  }

  function loadRecords() {
    const stored = loadJson(STORAGE_KEY, []);
    const normalized = stored.map(normalizeRecord);
    if (JSON.stringify(stored) !== JSON.stringify(normalized)) saveJson(STORAGE_KEY, normalized);
    return normalized;
  }

  function openForm(record, defaults = {}) {
    form.reset();
    pendingFiles = { request: [], response: [], additional: [] };
    dialogTitle.textContent = record ? "Editar solicitud" : "Nueva solicitud";
    fields.id.value = record ? record.id : crypto.randomUUID();
    fields.requestDate.value = record ? record.requestDate : new Date().toISOString().slice(0, 10);
    fields.requester.value = record ? record.requester : "";
    fields.requestDocument.value = record ? record.requestDocument : "";
    fields.objective.value = record ? record.objective : "";
    fields.requestedInformation.value = record ? record.requestedInformation : "";
    fields.status.value = record ? record.status : defaults.status || "Recibido";
    fields.priority.value = record ? record.priority : "Media";
    fields.responseDate.value = record ? record.responseDate : "";
    fields.responseDocument.value = record ? record.responseDocument : "";
    fields.observations.value = record ? record.observations : "";
    document.querySelector("#request-attachment-message").textContent = "";
    renderAttachmentList(record);
    syncDatePicker(fields.requestDate, fields.requestDatePicker);
    syncDatePicker(fields.responseDate, fields.responseDatePicker);
    syncResponseDocumentRequirement();
    syncDateValidity();
    dialog.showModal();
    fields.requester.focus();
  }

  function readForm() {
    const existing = records.find((item) => item.id === fields.id.value);
    return {
      id: fields.id.value,
      requester: fields.requester.value.trim(),
      requestDocument: fields.requestDocument.value.trim(),
      requestDate: fields.requestDate.value,
      objective: fields.objective.value.trim(),
      requestedInformation: fields.requestedInformation.value.trim(),
      status: fields.status.value,
      priority: fields.priority.value,
      responseDate: fields.responseDate.value,
      responseDocument: fields.responseDocument.value.trim(),
      observations: fields.observations.value.trim(),
      attachments: existing?.attachments || [],
      ...(existing?.attachmentFolder ? { attachmentFolder: existing.attachmentFolder } : {}),
      ...(existing?.updatedAt ? { updatedAt: existing.updatedAt } : {})
    };
  }

  function normalizeRecord(record) {
    return {
      id: record.id || crypto.randomUUID(),
      requester: record.requester || "",
      requestDocument: record.requestDocument || "",
      requestDate: record.requestDate || "",
      objective: record.objective || "",
      requestedInformation: record.requestedInformation || "",
      status: normalizeStatus(record.status),
      priority: PRIORITIES.includes(record.priority) ? record.priority : "Media",
      responseDate: record.responseDate || "",
      responseDocument: record.responseDocument || "",
      observations: record.observations || "",
      attachments: Array.isArray(record.attachments) ? record.attachments.filter(validAttachment) : [],
      ...(record.attachmentFolder ? { attachmentFolder: record.attachmentFolder } : {}),
      ...(record.updatedAt ? { updatedAt: record.updatedAt } : {})
    };
  }

  function syncResponseDocumentRequirement() {
    fields.responseDocument.required = Boolean(fields.responseDate.value);
  }

  function syncDatePicker(textInput, datePicker) {
    datePicker.value = isValidIsoDate(textInput.value) ? textInput.value : "";
  }

  function selectCalendarDate(datePicker, textInput) {
    textInput.value = datePicker.value;
    textInput.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function syncDateValidity() {
    for (const input of [fields.requestDate, fields.responseDate]) {
      const valid = !input.value || isValidIsoDate(input.value);
      input.setCustomValidity(valid ? "" : "Usa una fecha válida con formato AAAA-MM-DD");
    }
  }

  function isValidIsoDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!match) return false;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const date = new Date(Date.UTC(year, month - 1, day));
    return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
  }

  function sortedRecords(values = records) {
    return [...values].sort((left, right) =>
      (left.requestDate || "9999-12-31").localeCompare(right.requestDate || "9999-12-31") ||
      left.id.localeCompare(right.id)
    );
  }

  function requestNumber(id) {
    return sortedRecords().findIndex((record) => record.id === id) + 1;
  }

  function normalizeStatus(value) {
    const normalized = value === "En proceso" ? "En formalización" : value;
    return STATUSES.includes(normalized) ? normalized : STATUSES[0];
  }

  async function saveFromDialog(event) {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const record = readForm();
    const existingIndex = records.findIndex((item) => item.id === record.id);
    if (existingIndex >= 0) {
      records[existingIndex] = record;
    } else {
      records.push(record);
    }
    const submit = form.querySelector('button[type="submit"]');
    const message = document.querySelector("#request-attachment-message");
    submit.disabled = true;
    try {
      await saveRecords();
      if (Object.values(pendingFiles).some((files) => files.length)) {
        message.textContent = "Guardando documentos localmente…";
        await uploadPendingFiles(record);
        await saveRecords();
      }
      render();
      dialog.close();
    } catch (error) {
      message.textContent = error.message || "No fue posible guardar los documentos.";
      message.classList.add("error");
    } finally {
      submit.disabled = false;
    }
  }

  function validAttachment(value) {
    return value && typeof value.id === "string" && typeof value.name === "string" &&
      ["request", "response", "additional"].includes(value.role);
  }

  function handleAttachmentAction(event) {
    const picker = event.target.closest("[data-request-file-picker]");
    if (picker) {
      const inputs = { request: fields.requestPdf, response: fields.responsePdf, additional: fields.additionalPdfs };
      inputs[picker.dataset.requestFilePicker]?.click();
      return;
    }
    const view = event.target.closest("[data-request-pdf-view]");
    if (view) openPdfViewer(fields.id.value, view.dataset.requestPdfView, view.dataset.requestPdfName);
  }

  function selectPendingFiles(role, fileList) {
    const files = [...(fileList || [])];
    const invalid = files.find((file) => !file.name.toLowerCase().endsWith(".pdf") || file.size > 25 * 1024 * 1024);
    const message = document.querySelector("#request-attachment-message");
    message.classList.remove("error");
    if (invalid) {
      message.textContent = "Selecciona archivos PDF de máximo 25 MB.";
      message.classList.add("error");
      return;
    }
    pendingFiles[role] = role === "additional" ? files : files.slice(0, 1);
    renderAttachmentList(records.find((item) => item.id === fields.id.value));
  }

  function renderAttachmentList(record) {
    const saved = record?.attachments || [];
    const pending = Object.entries(pendingFiles).flatMap(([role, files]) =>
      files.map((file) => ({ role, name: file.name, pending: true }))
    );
    const items = [...saved, ...pending];
    const container = document.querySelector("#request-attachment-list");
    container.innerHTML = items.length ? items.map((item) => `
      <div class="request-attachment-item">
        <span class="font-icon" aria-hidden="true">&#xEA90;</span>
        <span><strong>${escapeHtml(attachmentRoleLabel(item.role))}</strong><small>${escapeHtml(item.name)}</small></span>
        ${item.pending ? '<em>Pendiente</em>' : `<button type="button" data-request-pdf-view="${item.id}"
          data-request-pdf-name="${escapeHtml(item.name)}" aria-label="Ver ${escapeHtml(item.name)}">
          <span class="font-icon" aria-hidden="true">&#xE890;</span></button>`}
      </div>`).join("") : "";
  }

  function attachmentRoleLabel(role) {
    return role === "request" ? "Solicitud" : role === "response" ? "Respuesta" : "Adicional";
  }

  async function uploadPendingFiles(record) {
    const queue = Object.entries(pendingFiles).flatMap(([role, files]) => files.map((file) => ({ role, file })));
    for (const item of queue) {
      const body = new FormData();
      body.append("role", item.role);
      body.append("pdf", item.file);
      const response = await fetch(`/api/requests/${encodeURIComponent(record.id)}/attachments`, { method: "POST", body });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || `No fue posible subir ${item.file.name}`);
      const attachment = result.attachment;
      if (item.role === "additional") record.attachments.push(attachment);
      else record.attachments = record.attachments.filter((saved) => saved.role !== item.role).concat(attachment);
      record.attachmentFolder = attachment.folder;
    }
    pendingFiles = { request: [], response: [], additional: [] };
  }

  function render() {
    const query = searchInput.value.trim().toLowerCase();
    const priority = priorityFilter.value;
    const status = statusFilter.value;
    const filtered = sortedRecords().filter((record) => {
      const searchable = [
        record.requester,
        record.requestDocument,
        record.requestDate,
        record.objective,
        record.requestedInformation,
        record.status,
        record.priority,
        record.responseDate,
        record.responseDocument,
        record.observations
      ].join(" ").toLowerCase();

      return (!query || searchable.includes(query)) &&
        (!priority || record.priority === priority) &&
        (!status || record.status === status);
    });

    body.innerHTML = filtered.map((record) => rowTemplate(record, requestNumber(record.id))).join("");
    emptyState.classList.toggle("visible", filtered.length === 0);
    updateMetrics();
    renderStatusBoard();
  }

  function selectRequestView(view) {
    const activeView = view === "board" ? "board" : "list";
    document.querySelectorAll("[data-request-view]").forEach((button) => {
      const active = button.dataset.requestView === activeView;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
    });
    document.querySelector("#request-list-view").classList.toggle("active", activeView === "list");
    document.querySelector("#request-board-view").classList.toggle("active", activeView === "board");
  }

  function renderStatusBoard() {
    const query = searchInput.value.trim().toLowerCase();
    const priority = priorityFilter.value;
    const visibleRecords = sortedRecords().filter((record) => {
      const searchable = [record.requester, record.requestDocument, record.requestDate, record.requestedInformation,
        record.objective, record.status, record.priority, record.responseDate, record.responseDocument,
        record.observations].join(" ").toLowerCase();
      return (!query || searchable.includes(query)) && (!priority || record.priority === priority);
    });
    statusBoard.innerHTML = STATUSES.map((status) => {
      const columnRecords = visibleRecords.filter((record) => record.status === status);
      return boardColumnTemplate(status, columnRecords);
    }).join("");
  }

  function boardColumnTemplate(status, columnRecords) {
    return `
      <section class="diary-board-column ${boardStatusClass(status)}" data-request-board-status="${escapeHtml(status)}">
        <header><div><i aria-hidden="true"></i><strong>${escapeHtml(status)}</strong><span>${columnRecords.length}</span></div></header>
        <div class="diary-board-cards">
          ${columnRecords.map(boardCardTemplate).join("")}
          ${columnRecords.length ? "" : '<p class="diary-board-empty">Sin solicitudes en este estado</p>'}
        </div>
        <button class="diary-board-add" type="button" data-request-board-action="add" data-status="${escapeHtml(status)}">
          <span class="font-icon" aria-hidden="true">&#xE710;</span><span>Agregar solicitud</span>
        </button>
      </section>`;
  }

  function boardCardTemplate(record) {
    return `
      <article class="diary-board-card request-board-card" data-request-id="${record.id}" tabindex="0">
        <div class="diary-board-card-meta">
          <span>N.° ${requestNumber(record.id)} · ${escapeHtml(record.requestDocument || "Sin documento")}</span>
        </div>
        <h2>${escapeHtml(record.requester)}</h2>
        <p>${escapeHtml(record.requestedInformation)}</p>
        <footer><span>${formatIsoDate(record.requestDate)}</span><span>${escapeHtml(record.priority)}</span></footer>
      </article>`;
  }

  function handleBoardClick(event) {
    if (suppressBoardClick) {
      event.preventDefault();
      return;
    }
    const addButton = event.target.closest('[data-request-board-action="add"]');
    if (addButton) openForm(null, { status: addButton.dataset.status });
  }

  function handleBoardPointerDown(event) {
    if (event.button !== 0 || event.target.closest("button, input, textarea, a")) return;
    const card = event.target.closest("[data-request-id]");
    if (!card) return;
    const bounds = card.getBoundingClientRect();
    pointerDrag = { card, id: card.dataset.requestId, pointerId: event.pointerId,
      startX: event.clientX, startY: event.clientY, offsetX: event.clientX - bounds.left,
      offsetY: event.clientY - bounds.top, moved: false, target: null, ghost: null, placeholder: null };
    card.setPointerCapture(event.pointerId);
  }

  function handleBoardPointerMove(event) {
    if (!pointerDrag || pointerDrag.pointerId !== event.pointerId) return;
    if (!pointerDrag.moved && Math.hypot(event.clientX - pointerDrag.startX, event.clientY - pointerDrag.startY) < 6) return;
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
    const column = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-request-board-status]");
    statusBoard.querySelectorAll(".drag-over").forEach((item) => item.classList.remove("drag-over"));
    pointerDrag.target = column && statusBoard.contains(column) ? column : null;
    if (pointerDrag.target) {
      pointerDrag.target.classList.add("drag-over");
      pointerDrag.target.querySelector(".diary-board-cards")?.append(pointerDrag.placeholder);
    } else pointerDrag.placeholder.remove();
  }

  function handleBoardPointerUp(event) {
    if (!pointerDrag || pointerDrag.pointerId !== event.pointerId) return;
    const { card, id, moved, target } = pointerDrag;
    if (card.hasPointerCapture(event.pointerId)) card.releasePointerCapture(event.pointerId);
    if (moved) {
      suppressBoardClick = true;
      setTimeout(() => { suppressBoardClick = false; }, 0);
    }
    const record = records.find((item) => item.id === id);
    if (moved && target && record && record.status !== target.dataset.requestBoardStatus) {
      record.status = target.dataset.requestBoardStatus;
      saveRecords();
      render();
    }
    clearBoardPointerDrag();
  }

  function cancelBoardPointerDrag(event) {
    if (pointerDrag?.pointerId === event.pointerId) clearBoardPointerDrag();
  }

  function clearBoardPointerDrag() {
    pointerDrag?.ghost?.remove();
    pointerDrag?.placeholder?.remove();
    pointerDrag = null;
    document.body.classList.remove("diary-card-dragging");
    statusBoard.querySelectorAll(".dragging, .drag-over").forEach((item) => item.classList.remove("dragging", "drag-over"));
  }

  function createBoardDragGhost(drag) {
    const ghost = drag.card.cloneNode(true);
    ghost.className = "diary-board-drag-ghost";
    ghost.removeAttribute("data-request-id");
    ghost.removeAttribute("tabindex");
    ghost.style.width = `${drag.card.getBoundingClientRect().width}px`;
    document.body.append(ghost);
    return ghost;
  }

  function positionBoardDragGhost(drag, clientX, clientY) {
    drag.ghost.style.left = `${clientX - drag.offsetX}px`;
    drag.ghost.style.top = `${clientY - drag.offsetY}px`;
  }

  function handleRequestContextMenu(event) {
    const target = event.target.closest("[data-request-id]");
    if (!target) return;
    event.preventDefault();
    contextRecordId = target.dataset.requestId;
    contextMenu.hidden = false;
    const targetBounds = target.getBoundingClientRect();
    const x = event.clientX || targetBounds.left + 24;
    const y = event.clientY || targetBounds.top + 24;
    const bounds = contextMenu.getBoundingClientRect();
    contextMenu.style.left = `${Math.max(8, Math.min(x, window.innerWidth - bounds.width - 8))}px`;
    contextMenu.style.top = `${Math.max(8, Math.min(y, window.innerHeight - bounds.height - 8))}px`;
    contextMenu.querySelector("button")?.focus();
  }

  function handleContextMenuAction(event) {
    const button = event.target.closest("[data-request-menu-action]");
    if (!button) return;
    const record = records.find((item) => item.id === contextRecordId);
    closeContextMenu();
    if (!record) return;
    if (button.dataset.requestMenuAction === "edit") openForm(record);
    if (button.dataset.requestMenuAction === "open-folder") openRequestFolder(record);
    if (button.dataset.requestMenuAction === "delete") requestRecordDeletion(record);
  }

  async function openRequestFolder(record) {
    try {
      const response = await fetch(`/api/requests/${encodeURIComponent(record.id)}/folder/open`, { method: "POST" });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "No fue posible abrir la carpeta");
    } catch (error) {
      console.error(error);
    }
  }

  function dismissContextMenu(event) {
    if (!contextMenu.hidden && !contextMenu.contains(event.target)) closeContextMenu();
    if (!event.target.closest(".request-choice-control")) closeQuickChoiceMenus();
  }

  function closeContextMenu() {
    contextMenu.hidden = true;
    contextRecordId = "";
  }

  function requestRecordDeletion(record) {
    deleteRecordId = record.id;
    document.querySelector("#request-delete-message").textContent =
      `Se eliminará la solicitud de “${record.requester}”. Esta acción no se puede deshacer.`;
    document.querySelector("#request-delete-dialog").showModal();
  }

  async function confirmRecordDeletion(event) {
    event.preventDefault();
    if (deleteRecordId) {
      const response = await fetch(`/api/requests/${encodeURIComponent(deleteRecordId)}/documents`, { method: "DELETE" });
      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        document.querySelector("#request-delete-message").textContent =
          result.detail || "No fue posible eliminar la carpeta de documentos.";
        return;
      }
      records = records.filter((item) => item.id !== deleteRecordId);
      saveRecords();
      render();
    }
    deleteRecordId = "";
    document.querySelector("#request-delete-dialog").close("deleted");
  }

  function cancelRecordDeletion() {
    deleteRecordId = "";
    document.querySelector("#request-delete-dialog").close();
  }

  function boardStatusClass(status) {
    return {
      Recibido: "request-status-received",
      "En formalización": "request-status-formalizing",
      "Despachado por Quipux": "request-status-dispatched",
      Entregado: "request-status-delivered",
      Archivado: "request-status-archived"
    }[status] || "";
  }

  function rowTemplate(record, number) {
    return `
      <tr data-request-id="${record.id}" tabindex="0" aria-label="Solicitud ${number} de ${escapeHtml(record.requester)}">
        <td><strong>${number}</strong></td>
        <td><strong>${escapeHtml(record.requester)}</strong></td>
        <td>${documentCellTemplate(record, "request", record.requestDocument)}</td>
        <td class="date-cell">${formatIsoDate(record.requestDate)}</td>
        <td class="text-cell">${escapeHtml(record.objective)}</td>
        <td class="text-cell">${escapeHtml(record.requestedInformation)}</td>
        <td class="request-choice-cell">${choiceControlTemplate(record, "status", STATUSES)}</td>
        <td>${escapeHtml(record.priority)}</td>
        <td class="date-cell">${formatIsoDate(record.responseDate)}</td>
        <td>${documentCellTemplate(record, "response", record.responseDocument)}</td>
        <td class="text-cell">${escapeHtml(record.observations)}</td>
      </tr>
    `;
  }

  function documentCellTemplate(record, role, documentNumber) {
    const attachment = record.attachments.find((item) => item.role === role);
    return `<span class="request-document-cell"><span>${escapeHtml(documentNumber)}</span>${attachment ? `
      <button type="button" data-request-pdf-view="${attachment.id}" data-request-id="${record.id}"
        data-request-pdf-name="${escapeHtml(attachment.name)}" aria-label="Ver PDF ${escapeHtml(attachment.name)}"
        title="Ver PDF"><span class="font-icon" aria-hidden="true">&#xE890;</span></button>` : ""}</span>`;
  }

  function formatIsoDate(value) {
    return /^\d{4}-\d{2}-\d{2}$/.test(value || "") ? value : "";
  }

  function handlePdfViewClick(event) {
    const button = event.target.closest("[data-request-pdf-view]");
    if (!button) return;
    event.stopPropagation();
    openPdfViewer(button.dataset.requestId, button.dataset.requestPdfView, button.dataset.requestPdfName);
  }

  function openPdfViewer(recordId, attachmentId, name) {
    const viewer = document.querySelector("#request-pdf-dialog");
    document.querySelector("#request-pdf-title").textContent = name || "Documento PDF";
    document.querySelector("#request-pdf-frame").src =
      `/api/requests/${encodeURIComponent(recordId)}/attachments/${encodeURIComponent(attachmentId)}/content`;
    viewer.showModal();
  }

  function closePdfViewer() {
    document.querySelector("#request-pdf-frame").src = "about:blank";
    document.querySelector("#request-pdf-dialog").close();
  }

  function choiceControlTemplate(record, field, values) {
    const current = record.status;
    const label = "Estado";
    return `
      <div class="request-choice-control">
        <button class="request-choice-toggle ${choiceClass(field, current)}" type="button"
          data-request-choice-toggle aria-haspopup="menu" aria-expanded="false"
          aria-label="Cambiar ${label.toLowerCase()} de ${escapeHtml(record.requester)}">
          <span>${escapeHtml(current)}</span><span class="font-icon" aria-hidden="true">&#xE70D;</span>
        </button>
        <div class="request-choice-menu" role="menu" hidden>
          ${values.map((value) => `
            <button type="button" role="menuitemradio" aria-checked="${current === value}"
              data-request-choice-id="${record.id}" data-request-choice-field="${field}"
              data-request-choice-value="${escapeHtml(value)}">
              <i class="${choiceClass(field, value)}" aria-hidden="true"></i><span>${escapeHtml(value)}</span>
            </button>
          `).join("")}
        </div>
      </div>`;
  }

  function handleQuickChoice(event) {
    const toggle = event.target.closest("[data-request-choice-toggle]");
    if (toggle) {
      const menu = toggle.nextElementSibling;
      const opening = menu.hidden;
      closeQuickChoiceMenus();
      menu.hidden = !opening;
      toggle.setAttribute("aria-expanded", String(opening));
      if (opening) positionQuickChoiceMenu(toggle, menu);
      return;
    }
    const option = event.target.closest("[data-request-choice-value]");
    if (!option) return;
    const record = records.find((item) => item.id === option.dataset.requestChoiceId);
    const field = option.dataset.requestChoiceField;
    if (!record || field !== "status") return;
    record.status = option.dataset.requestChoiceValue;
    saveRecords();
    render();
  }

  function closeQuickChoiceMenus() {
    document.querySelectorAll(".request-choice-menu:not([hidden])").forEach((menu) => {
      menu.hidden = true;
      menu.previousElementSibling?.setAttribute("aria-expanded", "false");
    });
  }

  function positionQuickChoiceMenu(toggle, menu) {
    const toggleBounds = toggle.getBoundingClientRect();
    const menuBounds = menu.getBoundingClientRect();
    const roomBelow = window.innerHeight - toggleBounds.bottom;
    const top = roomBelow >= menuBounds.height + 8
      ? toggleBounds.bottom + 5
      : Math.max(8, toggleBounds.top - menuBounds.height - 5);
    menu.style.left = `${Math.min(toggleBounds.left, window.innerWidth - menuBounds.width - 8)}px`;
    menu.style.top = `${top}px`;
  }

  function choiceClass(field, value) {
    return {
      Recibido: "choice-received",
      "En formalización": "choice-formalizing",
      "Despachado por Quipux": "choice-dispatched",
      Entregado: "choice-delivered",
      Archivado: "choice-archived"
    }[value] || "choice-received";
  }

  function updateMetrics() {
    document.querySelector("#metric-total").textContent = records.length;
    document.querySelector("#metric-received").textContent = records.filter((item) => item.status === "Recibido").length;
    document.querySelector("#metric-formalizing").textContent = records.filter((item) => item.status === "En formalización").length;
    document.querySelector("#metric-delivered").textContent = records.filter((item) => item.status === "Entregado").length;
  }

  async function exportExcel() {
    const headers = [
      "N.°",
      "Nombre del solicitante",
      "N.° de documento de solicitud",
      "Fecha de solicitud",
      "Objetivo de la solicitud",
      "Información solicitada",
      "Estado",
      "Prioridad",
      "Fecha de respuesta",
      "N.° de documento de respuesta",
      "Observaciones"
    ];
    const rows = sortedRecords().map((record) => [
      requestNumber(record.id),
      record.requester,
      record.requestDocument,
      record.requestDate,
      record.objective,
      record.requestedInformation,
      record.status,
      record.priority,
      record.responseDate,
      record.responseDocument,
      record.observations
    ]);
    const button = document.querySelector("#export-excel");
    const label = button.querySelector("span:last-child");
    button.disabled = true;
    label.textContent = "Generando…";
    try {
      const response = await fetch("/api/requests/export-excel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: `tabla-solicitudes-${new Date().toISOString().slice(0, 10)}`,
          headers,
          rows
        })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "No fue posible exportar la tabla");
      if (result.saved) {
        label.textContent = "Guardado";
        button.title = `Archivo guardado como ${result.filename}`;
      }
    } catch (error) {
      label.textContent = "Error";
      button.title = error.message;
      console.error(error);
    } finally {
      window.setTimeout(() => {
        button.disabled = false;
        label.textContent = "Exportar";
      }, 1200);
    }
  }

  window.NotasRequests = {
    initRequests
  };
})();

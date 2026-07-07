(function () {
  const STORAGE_KEY = "agender.request.records";
  const { csvEscape, escapeHtml, formatDate, normalizeDate, parseCsv } = window.NotasUtils;
  const { loadJson, saveJson } = window.NotasStorage;

  const sampleRecord = {
    id: crypto.randomUUID(),
    requester: "Adriana Stumba Nauta",
    reference: "",
    requestDate: "2025-12-06",
    requestedData: "Precipitacion\nTemperatura (maxima, minima, media)\nHumedad relativa (maxima, minima, media)\nRadiacion solar (media), caudales",
    objective: "Desarrollar y evaluar un marco de modelacion de la demanda de agua por tipo de uso, que integre factores climaticos, socioeconomicos y temporales, con el proposito de caracterizar sus patrones de variabilidad.",
    result: "Aceptado",
    status: "Entregado",
    deliveryDate: ""
  };

  let records = [];
  let fields;
  let body;
  let dialog;
  let form;
  let dialogTitle;
  let emptyState;
  let searchInput;
  let resultFilter;
  let statusFilter;
  let csvFile;

  function initRequests() {
    fields = {
      id: document.querySelector("#record-id"),
      requester: document.querySelector("#requester"),
      reference: document.querySelector("#reference"),
      requestDate: document.querySelector("#request-date"),
      requestedData: document.querySelector("#requested-data"),
      objective: document.querySelector("#request-objective"),
      result: document.querySelector("#request-result"),
      status: document.querySelector("#status"),
      deliveryDate: document.querySelector("#delivery-date")
    };

    body = document.querySelector("#requests-body");
    dialog = document.querySelector("#request-dialog");
    form = document.querySelector("#request-form");
    dialogTitle = document.querySelector("#dialog-title");
    emptyState = document.querySelector("#empty-state");
    searchInput = document.querySelector("#search-input");
    resultFilter = document.querySelector("#request-filter");
    statusFilter = document.querySelector("#status-filter");
    csvFile = document.querySelector("#csv-file");
    records = loadJson(STORAGE_KEY, []);

    if (records.length === 0) {
      records = [sampleRecord];
      saveRecords();
    }

    document.querySelector("#new-request").addEventListener("click", () => openForm());
    document.querySelector("#export-csv").addEventListener("click", exportCsv);
    document.querySelector("#import-csv").addEventListener("click", () => csvFile.click());
    csvFile.addEventListener("change", importCsv);
    searchInput.addEventListener("input", render);
    resultFilter.addEventListener("change", render);
    statusFilter.addEventListener("change", render);

    form.addEventListener("submit", saveFromDialog);
    body.addEventListener("click", handleTableClick);

    render();
  }

  function saveRecords() {
    saveJson(STORAGE_KEY, records);
  }

  function openForm(record) {
    form.reset();
    dialogTitle.textContent = record ? "Editar solicitud" : "Nueva solicitud";
    fields.id.value = record ? record.id : crypto.randomUUID();
    fields.requestDate.value = record ? record.requestDate : new Date().toISOString().slice(0, 10);
    fields.requester.value = record ? record.requester : "";
    fields.reference.value = record ? record.reference : "";
    fields.requestedData.value = record ? record.requestedData : "";
    fields.objective.value = record ? record.objective : "";
    fields.result.value = record ? record.result : "Aceptado";
    fields.status.value = record ? record.status : "Recibido";
    fields.deliveryDate.value = record ? record.deliveryDate : "";
    dialog.showModal();
    fields.requester.focus();
  }

  function readForm() {
    return {
      id: fields.id.value,
      requester: fields.requester.value.trim(),
      reference: fields.reference.value.trim(),
      requestDate: fields.requestDate.value,
      requestedData: fields.requestedData.value.trim(),
      objective: fields.objective.value.trim(),
      result: fields.result.value,
      status: fields.status.value,
      deliveryDate: fields.deliveryDate.value
    };
  }

  function saveFromDialog(event) {
    event.preventDefault();

    const record = readForm();
    const existingIndex = records.findIndex((item) => item.id === record.id);
    if (existingIndex >= 0) {
      records[existingIndex] = record;
    } else {
      records.unshift(record);
    }
    saveRecords();
    render();
    dialog.close();
  }

  function handleTableClick(event) {
    const button = event.target.closest("button");
    if (!button) return;

    const id = button.dataset.id;
    const record = records.find((item) => item.id === id);
    if (!record) return;

    if (button.dataset.action === "edit") openForm(record);

    if (button.dataset.action === "delete") {
      const confirmed = confirm("Eliminar esta solicitud?");
      if (!confirmed) return;
      records = records.filter((item) => item.id !== id);
      saveRecords();
      render();
    }
  }

  function render() {
    const query = searchInput.value.trim().toLowerCase();
    const result = resultFilter.value;
    const status = statusFilter.value;
    const filtered = records.filter((record) => {
      const searchable = [
        record.requester,
        record.reference,
        record.requestDate,
        record.requestedData,
        record.objective,
        record.result,
        record.status,
        record.deliveryDate
      ].join(" ").toLowerCase();

      return (!query || searchable.includes(query)) &&
        (!result || record.result === result) &&
        (!status || record.status === status);
    });

    body.innerHTML = filtered.map(rowTemplate).join("");
    emptyState.classList.toggle("visible", filtered.length === 0);
    updateMetrics();
  }

  function rowTemplate(record) {
    return `
      <tr>
        <td><strong>${escapeHtml(record.requester)}</strong></td>
        <td>${escapeHtml(record.reference)}</td>
        <td class="date-cell">${formatDate(record.requestDate)}</td>
        <td class="text-cell">${escapeHtml(record.requestedData)}</td>
        <td class="text-cell">${escapeHtml(record.objective)}</td>
        <td><span class="status-pill ${pillClass(record.result)}">${escapeHtml(record.result)}</span></td>
        <td><span class="status-pill ${pillClass(record.status)}">${escapeHtml(record.status)}</span></td>
        <td class="date-cell">${formatDate(record.deliveryDate)}</td>
        <td>
          <div class="row-actions">
            <button type="button" data-action="edit" data-id="${record.id}">Editar</button>
            <button class="danger" type="button" data-action="delete" data-id="${record.id}">Borrar</button>
          </div>
        </td>
      </tr>
    `;
  }

  function updateMetrics() {
    document.querySelector("#metric-total").textContent = records.length;
    document.querySelector("#metric-pending").textContent = records.filter((item) => item.result === "Pendiente" || item.status === "En proceso").length;
    document.querySelector("#metric-accepted").textContent = records.filter((item) => item.result === "Aceptado").length;
    document.querySelector("#metric-delivered").textContent = records.filter((item) => item.status === "Entregado").length;
  }

  function pillClass(value) {
    const normalized = value.toLowerCase();
    if (normalized.includes("aceptado")) return "status-accepted";
    if (normalized.includes("entregado")) return "status-delivered";
    if (normalized.includes("rechazado")) return "status-rejected";
    if (normalized.includes("revision")) return "status-review";
    return "status-pending";
  }

  function exportCsv() {
    const headers = [
      "Solicitante",
      "Nro. Referencia",
      "Fecha solicitud",
      "Datos Solicitados",
      "Objetivo de solicitud",
      "Solicitud",
      "Estado",
      "Fecha entrega"
    ];
    const rows = records.map((record) => [
      record.requester,
      record.reference,
      record.requestDate,
      record.requestedData,
      record.objective,
      record.result,
      record.status,
      record.deliveryDate
    ]);
    const csv = [headers, ...rows].map((row) => row.map(csvEscape).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `solicitud-datos-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function importCsv(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      const rows = parseCsv(String(reader.result));
      const imported = rows.slice(1).filter((row) => row.length >= 8).map((row) => ({
        id: crypto.randomUUID(),
        requester: row[0] || "",
        reference: row[1] || "",
        requestDate: normalizeDate(row[2]),
        requestedData: row[3] || "",
        objective: row[4] || "",
        result: row[5] || "Pendiente",
        status: row[6] || "Recibido",
        deliveryDate: normalizeDate(row[7])
      }));
      records = [...imported, ...records];
      saveRecords();
      render();
      csvFile.value = "";
    };
    reader.readAsText(file);
  }

  window.NotasRequests = {
    initRequests
  };
})();

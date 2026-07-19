(function () {
  let modal;
  let frame;
  let title;
  let contextMenu;
  let downloadModal;
  let downloadForm;
  let downloadSession;
  let downloadBusy = false;
  let downloadRequestId = 0;
  let batchModal;
  let batchStations = [];
  let batchSelected = new Set();
  let batchSource = "raw";

  function initViewer() {
    modal = document.querySelector("#station-viewer-modal");
    frame = document.querySelector("#station-viewer-frame");
    title = document.querySelector("#station-viewer-title");
    contextMenu = document.querySelector("#station-context-menu");
    downloadModal = document.querySelector("#station-download-modal");
    downloadForm = document.querySelector("#station-download-form");
    batchModal = document.querySelector("#station-batch-modal");
    frame.addEventListener("load", () => {
      if (frame.src === "about:blank") return;
      modal.classList.remove("is-loading");
    });
    document.querySelector("#station-viewer-close").addEventListener("click", closeViewer);
    modal.addEventListener("click", (event) => {
      if (event.target === modal) closeViewer();
    });
    contextMenu.addEventListener("click", (event) => {
      const action = event.target.closest("[data-viewer-action]");
      if (!action) return;
      if (action.dataset.viewerAction === "download") {
        openDownload(contextMenu.dataset.code, contextMenu.dataset.source);
      } else {
        openViewer(contextMenu.dataset.code, contextMenu.dataset.source);
      }
    });
    downloadForm.addEventListener("submit", downloadData);
    downloadModal.addEventListener("click", (event) => {
      if (event.target === downloadModal) closeDownload();
    });
    downloadModal.querySelector(".station-download-close").addEventListener("click", closeDownload);
    downloadModal.querySelector(".station-download-cancel").addEventListener("click", closeDownload);
    document.querySelector("#station-download-all").addEventListener("change", toggleAllVariables);
    document.querySelector("#station-download-variables").addEventListener("change", syncAllVariables);
    document.querySelector("#station-download-resolution").addEventListener("change", syncCoverageState);
    document.querySelector("#station-download-start").addEventListener("change", validateDownloadRange);
    document.querySelector("#station-download-end").addEventListener("change", validateDownloadRange);
    document.querySelector("#station-download-custom-value").addEventListener("input", updateDownloadSubmitState);
    document.querySelector("#station-download-coverage").addEventListener("input", updateDownloadSubmitState);
    document.querySelector("#station-batch-form").addEventListener("submit", downloadBatch);
    batchModal.addEventListener("click", (event) => {
      if (event.target === batchModal) closeBatchDownload();
    });
    batchModal.querySelector(".station-batch-close").addEventListener("click", closeBatchDownload);
    batchModal.querySelector(".station-batch-cancel").addEventListener("click", closeBatchDownload);
    document.querySelector("#station-batch-all").addEventListener("change", toggleAllBatchStations);
    document.querySelector("#station-batch-list").addEventListener("change", handleBatchStationChange);
    document.querySelector("#station-batch-search").addEventListener("input", renderBatchStations);
    document.querySelector("#station-batch-resolution").addEventListener("change", syncBatchCustom);
    document.querySelector("#station-batch-custom-value").addEventListener("input", updateBatchSubmit);
    document.querySelector("#station-batch-coverage").addEventListener("input", updateBatchSubmit);
    document.addEventListener("pointerdown", (event) => {
      if (!event.target.closest("#station-context-menu")) hideContextMenu();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (!contextMenu.hidden) hideContextMenu();
      else if (!downloadModal.hidden) closeDownload();
      else if (!batchModal.hidden) closeBatchDownload();
      else if (!modal.hidden) closeViewer();
    });
    window.addEventListener("message", (event) => {
      if (event.origin === window.location.origin && event.data?.type === "agender:close-viewer") closeViewer();
    });
  }

  function showContextMenu(event, code, source) {
    if (!document.body.dataset.modules.split(" ").includes("viewer")) return;
    event.preventDefault();
    contextMenu.dataset.code = code;
    contextMenu.dataset.source = source;
    contextMenu.querySelector(".station-context-label").textContent = code;
    contextMenu.hidden = false;
    const bounds = contextMenu.getBoundingClientRect();
    contextMenu.style.left = `${Math.max(8, Math.min(event.clientX, innerWidth - bounds.width - 8))}px`;
    contextMenu.style.top = `${Math.max(8, Math.min(event.clientY, innerHeight - bounds.height - 8))}px`;
  }

  function hideContextMenu() {
    contextMenu.hidden = true;
  }

  function openViewer(code, source) {
    if (!code) return;
    hideContextMenu();
    title.textContent = `Viewer · ${code}`;
    modal.classList.add("is-loading");
    modal.hidden = false;
    frame.src = `/viewer/?station=${encodeURIComponent(code)}&source=${encodeURIComponent(source || "raw")}`;
    document.body.classList.add("viewer-open");
    document.querySelector("#station-viewer-close").focus();
  }

  function closeViewer() {
    modal.hidden = true;
    modal.classList.remove("is-loading");
    frame.src = "about:blank";
    document.body.classList.remove("viewer-open");
  }

  function setDownloadMessage(message, isError = false) {
    const element = document.querySelector("#station-download-message");
    element.textContent = message;
    element.classList.toggle("is-error", isError);
  }

  async function responseError(response, fallback) {
    try {
      const payload = await response.json();
      return payload.detail || fallback;
    } catch {
      return fallback;
    }
  }

  async function openDownload(code, source) {
    if (!code) return;
    const requestId = ++downloadRequestId;
    hideContextMenu();
    downloadSession = null;
    downloadForm.reset();
    downloadForm.dataset.failed = "false";
    downloadForm.dataset.rangeInvalid = "false";
    document.querySelector("#station-download-all").checked = true;
    document.querySelector("#station-download-subtitle").textContent = `${code} · ${source === "quality" ? "Control de calidad" : "Datos crudos"}`;
    document.querySelector("#station-download-variables").innerHTML = "";
    downloadForm.dataset.code = code;
    downloadForm.dataset.source = source || "raw";
    downloadForm.classList.add("is-preparing");
    downloadModal.hidden = false;
    document.body.classList.add("download-open");
    setDownloadMessage("Preparando las variables disponibles…");
    setDownloadBusy(true);
    try {
      const response = await fetch(
        `/viewer-api/api/stations/${encodeURIComponent(code)}?source=${encodeURIComponent(source || "raw")}`,
        { method: "POST" }
      );
      if (!response.ok) throw new Error(await responseError(response, "No fue posible abrir la estación."));
      if (requestId !== downloadRequestId) return;
      downloadSession = await response.json();
      renderVariables(downloadSession.variables);
      setDownloadDates(downloadSession.first_date, downloadSession.last_date);
      setDownloadMessage(`${downloadSession.total_rows.toLocaleString("es-CO")} registros disponibles.`);
      setDownloadBusy(false);
      downloadForm.classList.remove("is-preparing");
      document.querySelector("#station-download-submit").focus();
    } catch (error) {
      if (requestId !== downloadRequestId) return;
      setDownloadMessage(error.message, true);
      setDownloadBusy(false, true);
      downloadForm.classList.remove("is-preparing");
    }
    syncCoverageState();
  }

  function renderVariables(variables) {
    const container = document.querySelector("#station-download-variables");
    container.innerHTML = "";
    variables.forEach((variable, index) => {
      const label = document.createElement("label");
      const input = document.createElement("input");
      const text = document.createElement("span");
      input.type = "checkbox";
      input.name = "download-variable";
      input.value = variable;
      input.checked = true;
      input.id = `station-download-variable-${index}`;
      text.textContent = variable;
      label.append(input, text);
      container.appendChild(label);
    });
  }

  function toggleAllVariables(event) {
    document.querySelectorAll('input[name="download-variable"]').forEach((input) => {
      input.checked = event.target.checked;
    });
    event.target.indeterminate = false;
  }

  function syncAllVariables() {
    const inputs = Array.from(document.querySelectorAll('input[name="download-variable"]'));
    const checked = inputs.filter((input) => input.checked).length;
    const selectAll = document.querySelector("#station-download-all");
    selectAll.checked = checked === inputs.length;
    selectAll.indeterminate = checked > 0 && checked < inputs.length;
  }

  function syncCoverageState() {
    const custom = document.querySelector("#station-download-resolution").value === "custom";
    document.querySelector("#station-download-custom").hidden = !custom;
    updateDownloadSubmitState();
  }

  function setDownloadBusy(busy, failed = false) {
    downloadBusy = busy;
    downloadForm.dataset.failed = String(failed);
    document.querySelector("#station-download-submit").textContent = busy ? "Preparando…" : "Descargar";
    updateDownloadSubmitState();
  }

  function setDownloadDates(firstDate, lastDate) {
    const start = document.querySelector("#station-download-start");
    const end = document.querySelector("#station-download-end");
    start.value = firstDate || "";
    end.value = lastDate || "";
    start.min = firstDate || "";
    start.max = lastDate || "";
    end.min = firstDate || "";
    end.max = lastDate || "";
    validateDownloadRange();
  }

  function validateDownloadRange() {
    const start = document.querySelector("#station-download-start");
    const end = document.querySelector("#station-download-end");
    const warning = document.querySelector("#station-download-range-warning");
    const first = downloadSession?.first_date || "";
    const last = downloadSession?.last_date || "";
    let message = "";
    if (start.value && end.value && start.value > end.value) {
      message = "La fecha inicial no puede ser posterior a la fecha final.";
    } else if ((first && start.value < first) || (last && start.value > last)) {
      message = `La fecha inicial está fuera del rango disponible: ${first} a ${last}.`;
    } else if ((first && end.value < first) || (last && end.value > last)) {
      message = `La fecha final está fuera del rango disponible: ${first} a ${last}.`;
    }
    start.setCustomValidity(message);
    end.setCustomValidity(message);
    warning.textContent = message;
    warning.hidden = !message;
    downloadForm.dataset.rangeInvalid = String(Boolean(message));
    updateDownloadSubmitState();
    return !message;
  }

  function updateDownloadSubmitState() {
    const custom = document.querySelector("#station-download-resolution").value === "custom";
    const customInput = document.querySelector("#station-download-custom-value");
    const customInvalid = custom && !customInput.checkValidity();
    const coverageInvalid = !document.querySelector("#station-download-coverage").checkValidity();
    document.querySelector("#station-download-submit").disabled =
      downloadBusy ||
      downloadForm.dataset.failed === "true" ||
      downloadForm.dataset.rangeInvalid === "true" ||
      customInvalid ||
      coverageInvalid;
  }

  async function downloadData(event) {
    event.preventDefault();
    if (!downloadSession) return;
    if (!validateDownloadRange()) return;
    const variables = Array.from(document.querySelectorAll('input[name="download-variable"]:checked'))
      .map((input) => input.value);
    if (!variables.length) {
      setDownloadMessage("Selecciona al menos una variable.", true);
      return;
    }
    const payload = {
      session_id: downloadSession.session_id,
      station_code: downloadForm.dataset.code,
      variables,
      start_date: document.querySelector("#station-download-start").value || null,
      end_date: document.querySelector("#station-download-end").value || null,
      resolution: document.querySelector("#station-download-resolution").value,
      min_coverage: Number(document.querySelector("#station-download-coverage").value),
      file_format: document.querySelector("#station-download-format").value,
      custom_value: Number(document.querySelector("#station-download-custom-value").value),
      custom_unit: document.querySelector("#station-download-custom-unit").value,
      choose_destination: true
    };
    setDownloadBusy(true);
    setDownloadMessage("Generando el archivo…");
    try {
      const response = await fetch("/viewer-api/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error(await responseError(response, "No fue posible generar el archivo."));
      const result = await response.json();
      if (result.cancelled) {
        setDownloadMessage("Guardado cancelado.");
      } else {
        setDownloadMessage(`Archivo ${result.filename} guardado correctamente.`);
      }
    } catch (error) {
      setDownloadMessage(error.message, true);
    } finally {
      setDownloadBusy(false);
    }
  }

  function closeDownload() {
    downloadRequestId += 1;
    downloadModal.hidden = true;
    downloadSession = null;
    downloadForm.classList.remove("is-preparing");
    document.body.classList.remove("download-open");
  }

  function openBatchDownload(stations, source, context = {}) {
    batchStations = stations
      .filter((station) => station.fileCount > 0)
      .sort((a, b) => a.code.localeCompare(b.code, "es"));
    batchSelected = new Set();
    batchSource = source || "raw";
    document.querySelector("#station-batch-form").reset();
    document.querySelector("#station-batch-search").value = "";
    const sourceLabel = batchSource === "quality" ? "Control de calidad" : "Datos crudos";
    const availability = `${batchStations.length} estación${batchStations.length === 1 ? "" : "es"} disponible${batchStations.length === 1 ? "" : "s"}`;
    document.querySelector("#station-batch-subtitle").textContent = context.filtered
      ? `${sourceLabel} · ${availability} según los filtros actuales`
      : `${sourceLabel} · ${availability}`;
    setBatchMessage("");
    renderBatchStations();
    syncBatchCustom();
    batchModal.hidden = false;
    document.body.classList.add("download-open");
    document.querySelector("#station-batch-search").focus();
  }

  function renderBatchStations() {
    const query = document.querySelector("#station-batch-search").value.trim().toLocaleLowerCase("es");
    const visible = batchStations.filter((station) =>
      [station.code, station.type, station.basin].join(" ").toLocaleLowerCase("es").includes(query)
    );
    const container = document.querySelector("#station-batch-list");
    container.innerHTML = "";
    visible.forEach((station) => {
      const label = document.createElement("label");
      const input = document.createElement("input");
      const copy = document.createElement("span");
      const code = document.createElement("strong");
      const meta = document.createElement("small");
      input.type = "checkbox";
      input.value = station.code;
      input.checked = batchSelected.has(station.code);
      code.textContent = station.code;
      meta.textContent = [station.type, station.basin].filter(Boolean).join(" · ");
      copy.append(code, meta);
      label.append(input, copy);
      container.appendChild(label);
    });
    if (!visible.length) {
      const empty = document.createElement("p");
      empty.className = "station-batch-empty";
      empty.textContent = "No hay estaciones que coincidan.";
      container.appendChild(empty);
    }
    syncBatchSelectionState();
  }

  function toggleAllBatchStations(event) {
    if (event.target.checked) {
      batchStations.forEach((station) => batchSelected.add(station.code));
    } else {
      batchSelected.clear();
    }
    renderBatchStations();
  }

  function handleBatchStationChange(event) {
    const input = event.target.closest('input[type="checkbox"]');
    if (!input) return;
    if (input.checked) batchSelected.add(input.value);
    else batchSelected.delete(input.value);
    syncBatchSelectionState();
  }

  function syncBatchSelectionState() {
    const all = document.querySelector("#station-batch-all");
    all.checked = batchStations.length > 0 && batchSelected.size === batchStations.length;
    all.indeterminate = batchSelected.size > 0 && batchSelected.size < batchStations.length;
    document.querySelector("#station-batch-count").textContent =
      `${batchSelected.size} seleccionada${batchSelected.size === 1 ? "" : "s"}`;
    updateBatchSubmit();
  }

  function syncBatchCustom() {
    const custom = document.querySelector("#station-batch-resolution").value === "custom";
    document.querySelector("#station-batch-custom").hidden = !custom;
    updateBatchSubmit();
  }

  function updateBatchSubmit() {
    const form = document.querySelector("#station-batch-form");
    const custom = document.querySelector("#station-batch-resolution").value === "custom";
    const invalid =
      !document.querySelector("#station-batch-coverage").checkValidity() ||
      (custom && !document.querySelector("#station-batch-custom-value").checkValidity());
    document.querySelector("#station-batch-submit").disabled =
      form.dataset.busy === "true" || batchSelected.size === 0 || invalid;
  }

  function setBatchMessage(message, isError = false) {
    const element = document.querySelector("#station-batch-message");
    element.textContent = message;
    element.classList.toggle("is-error", isError);
  }

  async function downloadBatch(event) {
    event.preventDefault();
    if (!batchSelected.size) return;
    const form = event.currentTarget;
    form.dataset.busy = "true";
    document.querySelector("#station-batch-submit").textContent = "Preparando archivos…";
    setBatchMessage(`Preparando ${batchSelected.size} archivos. Selecciona una carpeta de destino…`);
    updateBatchSubmit();
    try {
      const response = await fetch("/viewer-api/api/export-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          station_codes: Array.from(batchSelected),
          source: batchSource,
          resolution: document.querySelector("#station-batch-resolution").value,
          min_coverage: Number(document.querySelector("#station-batch-coverage").value),
          file_format: document.querySelector("#station-batch-format").value,
          custom_value: Number(document.querySelector("#station-batch-custom-value").value),
          custom_unit: document.querySelector("#station-batch-custom-unit").value
        })
      });
      if (!response.ok) throw new Error(await responseError(response, "No fue posible generar el lote."));
      const result = await response.json();
      if (result.cancelled) {
        setBatchMessage("Descarga cancelada.");
      } else if (result.failed) {
        const failedCodes = result.errors.map((error) => error.station).join(", ");
        setBatchMessage(`${result.saved} archivos guardados; ${result.failed} no pudieron generarse: ${failedCodes}.`, true);
      } else {
        setBatchMessage(`${result.saved} archivos guardados correctamente en la carpeta seleccionada.`);
      }
    } catch (error) {
      setBatchMessage(error.message, true);
    } finally {
      form.dataset.busy = "false";
      document.querySelector("#station-batch-submit").textContent = "Elegir carpeta y descargar";
      updateBatchSubmit();
    }
  }

  function closeBatchDownload() {
    batchModal.hidden = true;
    batchStations = [];
    batchSelected.clear();
    document.body.classList.remove("download-open");
  }

  window.NotasViewer = { initViewer, showContextMenu, openViewer, openBatchDownload };
})();

(function () {
  const { escapeHtml } = window.NotasUtils;
  const { loadJson, saveJson } = window.NotasStorage;
  const { initHydrometMap, renderStationPoints, setVisibleBasins } = window.NotasHydrometMap;

  let hydrometStations = [];
  let selectedHydrometCode = "";
  let hydrometBody;
  let hydrometSearch;
  let hydrometFilterMenu;
  let hydrometFilterToggle;
  let hydrometMapPoints;
  let mapStationPopup;
  let mapPopupStation;
  let mapPopupScope;
  let mapPopupMeta;
  let mapPopupCompleteness;
  let mapPopupProgress;
  let mapPopupVariableCount;
  let mapPopupVariables;
  let completenessRecords = {};
  const syncingSources = new Set();
  let qcMethods = {};
  let selectedSource = localStorage.getItem("agender.hydromet.source") === "quality" ? "quality" : "raw";

  const averageExcludedVariables = new Set(["TIMESTAMP", "RECORD"]);
  const qcOptions = ["None", "V1", "V2", "V3"];
  const qcStorageKey = "agender.hydromet.qc-methods";
  const profileStorageKey = "agender.profile.preferences";
  const completionFilterOptions = [
    { value: "under50", label: "Menor a 50 %" },
    { value: "from51to70", label: "51 a 70 %" },
    { value: "from70to90", label: "70 a 90 %" },
    { value: "from90to100", label: "90 a 100 %" }
  ];
  const filterStates = {
    basin: { options: [], selected: null, allLabel: "Todas" },
    type: { options: [], selected: null, allLabel: "Todos" },
    completeness: { options: completionFilterOptions, selected: null, allLabel: "Todos" },
    variable: { options: [], selected: null, allLabel: "Todas las variables" }
  };

  function initHydromet() {
    const preferredSource = loadJson(profileStorageKey, {}).hydrometSource;
    if (preferredSource === "raw" || preferredSource === "quality") selectedSource = preferredSource;
    qcMethods = normalizeQcMethods(loadJson(qcStorageKey, {}));
    hydrometBody = document.querySelector("#hydromet-body");
    hydrometSearch = document.querySelector("#hydromet-search");
    hydrometFilterMenu = document.querySelector("#hydromet-filter-menu");
    hydrometFilterToggle = document.querySelector("#hydromet-filter-toggle");
    hydrometMapPoints = document.querySelector("#hydromet-map-points");
    mapStationPopup = document.querySelector("#map-station-popup");
    mapPopupStation = document.querySelector("#map-popup-station");
    mapPopupScope = document.querySelector("#map-popup-scope");
    mapPopupMeta = document.querySelector("#map-popup-meta");
    mapPopupCompleteness = document.querySelector("#map-popup-completeness");
    mapPopupProgress = document.querySelector("#map-popup-progress");
    mapPopupVariableCount = document.querySelector("#map-popup-variable-count");
    mapPopupVariables = document.querySelector("#map-popup-variables");
    initHydrometMap();
    bindEvents();
    updateSourceSwitch();
    const cached = restoreStationSnapshot(selectedSource);
    if (!cached) renderHydromet();
    updateConnectionStatus(`${sourceLabel()} · ${cached ? "inventario disponible · " : ""}actualizando…`, "server");
    syncLocalStations();
    setInterval(() => {
      if (!document.hidden) syncLocalStations();
    }, 5 * 60 * 1000);
  }

  function bindEvents() {
    hydrometSearch.addEventListener("input", renderHydromet);
    document.querySelector("#hydromet-filter-panel").addEventListener("click", handleMultiSelectClick);
    document.querySelector("#hydromet-filter-panel").addEventListener("change", handleMultiSelectChange);
    hydrometFilterToggle.addEventListener("click", toggleHydrometFilterMenu);
    document.querySelector("#hydromet-connection-status").addEventListener("click", syncLocalStations);
    document.querySelector("#hydromet-batch-download").addEventListener("click", () => {
      window.NotasViewer.openBatchDownload(
        getFilteredHydrometStations(),
        selectedSource,
        { filtered: hasActiveHydrometFilters() }
      );
    });
    document.querySelector("#hydromet-export").addEventListener("click", toggleExportPanel);
    document.querySelector("#hydromet-export-close").addEventListener("click", closeExportPanel);
    document.querySelector("#hydromet-export-all").addEventListener("change", handleExportSelectAll);
    document.querySelector("#hydromet-export-columns").addEventListener("change", syncExportOptions);
    document.querySelector("#hydromet-export-completeness-options").addEventListener("change", handleCompletenessModeChange);
    document.querySelector("#hydromet-export-confirm").addEventListener("click", exportHydrometExcel);
    document.querySelectorAll("[data-hydromet-source]").forEach((button) => {
      button.addEventListener("click", () => selectSource(button.dataset.hydrometSource));
    });
    document.addEventListener("click", handleDocumentClick);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeAllMultiSelects();
        closeHydrometFilterMenu();
        closeExportPanel();
      }
    });
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) syncLocalStations();
    });

    document.querySelectorAll("[data-hydromet-tab]").forEach((button) => {
      button.addEventListener("click", () => activateHydrometTab(button));
    });

    hydrometBody.addEventListener("click", handleTableClick);
    hydrometBody.addEventListener("click", handleQcEditClick);
    hydrometBody.addEventListener("change", handleQcMethodChange);
    hydrometBody.addEventListener("focusout", handleQcMethodBlur);
    hydrometBody.addEventListener("contextmenu", (event) => {
      const row = event.target.closest("tr[data-code]");
      if (!row) return;
      window.NotasViewer.showContextMenu(event, row.dataset.code, selectedSource);
    });
    hydrometMapPoints.addEventListener("click", (event) => {
      const point = event.target.closest("[data-code]");
      if (!point) return;
      selectedHydrometCode = point.dataset.code;
      renderHydromet();
    });
    hydrometMapPoints.addEventListener("contextmenu", (event) => {
      const point = event.target.closest("[data-code]");
      if (!point) return;
      window.NotasViewer.showContextMenu(event, point.dataset.code, selectedSource);
    });
    hydrometMapPoints.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const point = event.target.closest("[data-code]");
      if (!point) return;
      event.preventDefault();
      selectedHydrometCode = point.dataset.code;
      renderHydromet();
    });
    document.querySelector("#map-popup-close").addEventListener("click", () => {
      selectedHydrometCode = "";
      renderHydromet();
    });
  }

  function selectSource(source) {
    if (source === selectedSource) return;
    selectedSource = source;
    localStorage.setItem("agender.hydromet.source", source);
    window.NotasStorage.updateJson(profileStorageKey, { hydrometSource: source });
    updateSourceSwitch();
    if (!restoreStationSnapshot(source)) {
      hydrometStations = [];
      completenessRecords = {};
      fillHydrometFilters();
      renderHydromet();
    }
    updateConnectionStatus(`${sourceLabel()} · inventario disponible · actualizando…`, "server");
    syncLocalStations();
  }

  function updateSourceSwitch() {
    document.querySelectorAll("[data-hydromet-source]").forEach((button) => {
      const active = button.dataset.hydrometSource === selectedSource;
      button.classList.toggle("active", active);
      button.setAttribute("aria-checked", String(active));
    });
    const quality = selectedSource === "quality";
    document.querySelector("#hydromet-view").classList.toggle("quality-source", quality);
    document.querySelector("#hydromet-status-label").textContent = quality ? "QC asignado" : "Actualizadas";
    document.querySelector("#hydromet-status-header").textContent = quality ? "QC" : "Actualizada";
  }

  function handleTableClick(event) {
    if (event.target.closest("select, button, a, input")) return;
    const row = event.target.closest("tr[data-code]");
    if (!row) return;
    selectedHydrometCode = row.dataset.code;
    renderHydromet();
  }

  function toggleHydrometFilterMenu(event) {
    event.stopPropagation();
    const isOpen = hydrometFilterMenu.classList.toggle("open");
    hydrometFilterToggle.setAttribute("aria-expanded", String(isOpen));
  }

  function closeHydrometFilterMenu() {
    closeAllMultiSelects();
    hydrometFilterMenu.classList.remove("open");
    hydrometFilterToggle.setAttribute("aria-expanded", "false");
  }

  function handleDocumentClick(event) {
    if (!event.target.closest(".multi-select")) closeAllMultiSelects();
    if (!hydrometFilterMenu.contains(event.target)) closeHydrometFilterMenu();
    if (!event.target.closest("#hydromet-export-menu")) closeExportPanel();
  }

  function handleMultiSelectClick(event) {
    const button = event.target.closest(".multi-select-button");
    if (!button) return;
    event.stopPropagation();
    const control = button.closest(".multi-select");
    const willOpen = !control.classList.contains("open");
    closeAllMultiSelects();
    control.classList.toggle("open", willOpen);
    button.setAttribute("aria-expanded", String(willOpen));
  }

  function handleMultiSelectChange(event) {
    const input = event.target.closest(".multi-select-option input");
    if (!input) return;
    const control = input.closest(".multi-select");
    const key = control.dataset.hydrometFilter;
    const state = filterStates[key];
    const optionValues = state.options.map((option) => option.value);

    if (input.dataset.selectAll !== undefined) {
      state.selected = input.checked ? null : new Set();
    } else {
      const selected = state.selected === null ? new Set(optionValues) : new Set(state.selected);
      if (input.checked) selected.add(input.value);
      else selected.delete(input.value);
      state.selected = selected.size === optionValues.length ? null : selected;
    }

    renderMultiSelect(key);
    renderHydromet();
  }

  function closeAllMultiSelects() {
    document.querySelectorAll(".multi-select.open").forEach((control) => {
      control.classList.remove("open");
      control.querySelector(".multi-select-button").setAttribute("aria-expanded", "false");
    });
  }

  function activateHydrometTab(button) {
    const tab = button.dataset.hydrometTab;
    document.querySelector("#hydromet-view").classList.toggle("map-mode", tab === "map");
    document.querySelectorAll("[data-hydromet-tab]").forEach((item) => {
      item.classList.toggle("active", item === button);
      item.setAttribute("aria-selected", String(item === button));
    });
    document.querySelector("#hydromet-table-panel").classList.toggle("active", tab === "table");
    document.querySelector("#hydromet-map-panel").classList.toggle("active", tab === "map");
  }

  function fillHydrometFilters() {
    const basins = [...new Set(hydrometStations.map((station) => station.basin))].sort();
    const types = [...new Set(hydrometStations.map((station) => station.type))].sort();
    const variables = [...new Set(hydrometStations.flatMap(getVariablesForStation))]
      .filter(isAverageVariable)
      .sort();
    setMultiSelectOptions("basin", basins.map((value) => ({ value, label: value })));
    setMultiSelectOptions("type", types.map((value) => ({ value, label: value })));
    setMultiSelectOptions("completeness", completionFilterOptions);
    setMultiSelectOptions("variable", variables.map((value) => ({ value, label: value })));
  }

  function setMultiSelectOptions(key, options) {
    const state = filterStates[key];
    state.options = options;
    if (state.selected !== null) {
      const available = new Set(options.map((option) => option.value));
      state.selected = new Set([...state.selected].filter((value) => available.has(value)));
      if (state.selected.size === options.length) state.selected = null;
    }
    renderMultiSelect(key);
  }

  function renderMultiSelect(key) {
    const state = filterStates[key];
    const control = document.querySelector(`[data-hydromet-filter="${key}"]`);
    const flyout = control.querySelector(".multi-select-flyout");
    const selected = state.selected;
    flyout.innerHTML = `
      <label class="multi-select-option select-all">
        <input type="checkbox" data-select-all>
        <span>Seleccionar todo</span>
      </label>
      ${state.options.map((option) => `
        <label class="multi-select-option">
          <input type="checkbox" value="${escapeHtml(option.value)}">
          <span>${escapeHtml(option.label)}</span>
        </label>
      `).join("")}
    `;

    const selectAll = flyout.querySelector("[data-select-all]");
    selectAll.checked = selected === null;
    selectAll.indeterminate = selected !== null && selected.size > 0;
    flyout.querySelectorAll("input:not([data-select-all])").forEach((input) => {
      input.checked = selected === null || selected.has(input.value);
    });
    control.querySelector(".multi-select-summary").textContent = getMultiSelectSummary(state);
  }

  function getMultiSelectSummary(state) {
    if (state.selected === null) return state.allLabel;
    if (state.selected.size === 0) return "Ninguno";
    if (state.selected.size === 1) {
      const value = [...state.selected][0];
      const option = state.options.find((item) => item.value === value);
      return option ? option.label : value;
    }
    return `${state.selected.size} seleccionados`;
  }

  function matchesMultiSelect(key, value) {
    const selected = filterStates[key].selected;
    return selected === null || selected.has(value);
  }

  function getFilteredHydrometStations() {
    const query = hydrometSearch.value.trim().toLowerCase();
    return hydrometStations.filter((station) => {
      const searchable = [station.code, station.type, station.basin, station.start, station.end].join(" ").toLowerCase();
      return (!query || searchable.includes(query)) &&
        matchesMultiSelect("basin", station.basin) &&
        matchesMultiSelect("type", station.type) &&
        matchesVariableSelection(station) &&
        matchesCompletenessFilter(station);
    });
  }

  function hasActiveHydrometFilters() {
    return Boolean(hydrometSearch.value.trim()) ||
      Object.values(filterStates).some((state) => state.selected !== null);
  }

  function matchesVariableSelection(station) {
    const selected = filterStates.variable.selected;
    if (selected === null) return true;
    const stationVariables = getVariablesForStation(station);
    return [...selected].some((variable) => stationVariables.includes(variable));
  }

  function matchesCompletenessFilter(station) {
    const selected = filterStates.completeness.selected;
    if (selected === null) return true;
    if (selected.size === 0) return false;

    const average = getFilteredVariableCompleteness(station);
    if (average === null) return false;
    return [...selected].some((filter) => {
      if (filter === "under50") return average < 50;
      if (filter === "from51to70") return average >= 50 && average < 70;
      if (filter === "from70to90") return average >= 70 && average < 90;
      if (filter === "from90to100") return average >= 90 && average <= 100;
      return false;
    });
  }

  function renderHydromet() {
    const filtered = getFilteredHydrometStations();
    hydrometBody.innerHTML = filtered.map(hydrometRowTemplate).join("");
    renderHydrometMap(filtered);
    renderHydrometMetrics(filtered);
  }

  async function syncLocalStations() {
    const source = selectedSource;
    if (syncingSources.has(source)) return;
    syncingSources.add(source);
    updateConnectionStatus(`${sourceLabel(source)} · actualizando…`, "server");
    try {
      try {
        const snapshotResponse = await fetch(`/api/local-data?source=${source}&refresh=false`, {
          headers: { Accept: "application/json" },
          cache: "no-store"
        });
        if (snapshotResponse.ok) applyStationPayload(await snapshotResponse.json(), source);
      } catch (snapshotError) {
        console.warn("No fue posible cargar el último inventario", snapshotError);
      }

      const response = await fetch(`/api/local-data?source=${source}&refresh=true`, { headers: { Accept: "application/json" }, cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      applyStationPayload(payload, source);
      const updated = payload.generatedAt ? new Date(payload.generatedAt) : new Date();
      const time = new Intl.DateTimeFormat("es-CO", { hour: "2-digit", minute: "2-digit" }).format(updated);
      const fileLabel = `${payload.fileCount || 0} archivo${payload.fileCount === 1 ? "" : "s"}`;
      const processed = Number(payload.sync && payload.sync.processed) || 0;
      const remoteDownloaded = Number(payload.storage && payload.storage.remoteDownloaded) || 0;
      const syncLabel = remoteDownloaded
        ? `${remoteDownloaded} descargado${remoteDownloaded === 1 ? "" : "s"} de OneDrive`
        : processed ? `${processed} actualizado${processed === 1 ? "" : "s"}` : "sin cambios";
      if (selectedSource === source) {
        updateConnectionStatus(`${sourceLabel(source)} · ${fileLabel} · ${syncLabel} · ${time}`, "server");
      }
      if (Array.isArray(payload.warnings) && payload.warnings.length) console.warn(payload.warnings.join("\n"));
    } catch (error) {
      console.error("No fue posible leer los archivos locales", error);
      if (selectedSource === source) updateConnectionStatus(`${sourceLabel(source)} · no fue posible actualizar`, "error");
    } finally {
      syncingSources.delete(source);
      if (selectedSource === source) document.querySelector("#hydromet-connection-status").disabled = false;
    }
  }

  function applyStationPayload(payload, source) {
    cacheStationSnapshot(source, payload);
    if (selectedSource !== source) return;
    completenessRecords = {};
    hydrometStations = Array.isArray(payload.data) ? payload.data.map((row) => {
      const station = normalizeStation(row);
      completenessRecords[station.code] = { variables: row.completeness || {} };
      return station;
    }) : [];
    if (!hydrometStations.some((station) => station.code === selectedHydrometCode)) selectedHydrometCode = "";
    fillHydrometFilters();
    renderHydromet();
  }

  function restoreStationSnapshot(source) {
    try {
      const payload = JSON.parse(localStorage.getItem(`agender.hydromet.inventory.${source}`));
      if (!payload || !Array.isArray(payload.data)) return false;
      applyStationPayload(payload, source);
      return true;
    } catch {
      return false;
    }
  }

  function cacheStationSnapshot(source, payload) {
    try {
      localStorage.setItem(`agender.hydromet.inventory.${source}`, JSON.stringify(payload));
    } catch (error) {
      console.warn("No fue posible conservar el inventario hidrometeorológico", error);
    }
  }

  function sourceLabel(source = selectedSource) {
    return source === "quality" ? "Control de calidad" : "Datos crudos";
  }

  function normalizeStation(station) {
    return {
      ...station,
      code: station.code ?? station.codigo ?? "",
      transmission: station.transmission === true || station.transmission === 1 || station.transmission === "1",
      type: station.type ?? station.tipo ?? station.tipo_estacion ?? "",
      x: Number(station.x ?? station.x_utm ?? 0),
      y: Number(station.y ?? station.y_utm ?? 0),
      z: station.z ?? station.altitud ?? "",
      basin: station.basin ?? station.subcuenca ?? station.cuenca ?? "",
      start: dateOnly(station.start ?? station.primer_registro ?? station.fecha_inicio),
      end: dateOnly(station.end ?? station.ultimo_registro ?? station.fecha_fin),
      variables: Array.isArray(station.variables) ? station.variables : []
    };
  }

  function dateOnly(value) {
    if (!value) return "";
    const match = String(value).match(/^\d{4}-\d{2}-\d{2}/);
    return match ? match[0] : "";
  }

  function updateConnectionStatus(label, stateClass) {
    const badge = document.querySelector("#hydromet-connection-status");
    badge.textContent = label;
    badge.className = `connection-badge${stateClass ? ` ${stateClass}` : ""}`;
    badge.disabled = syncingSources.has(selectedSource);
    badge.title = "Sincronizar ahora";
  }

  function hydrometRowTemplate(station) {
    const selected = selectedHydrometCode === station.code ? " selected" : "";
    return `
      <tr class="${selected}" data-code="${escapeHtml(station.code)}">
        <td><strong>${escapeHtml(station.code)}</strong></td>
        <td class="transmission-column">${transmissionIconTemplate(station.transmission)}</td>
        <td>${escapeHtml(station.type)}</td>
        <td>${station.x}</td>
        <td>${station.y}</td>
        <td>${escapeHtml(station.z)}</td>
        <td>${escapeHtml(station.basin)}</td>
        <td class="date-cell">${escapeHtml(station.start || "Sin registro")}</td>
        <td class="date-cell">${escapeHtml(station.end || "Sin registro")}</td>
        <td>${selectedSource === "quality" ? qcMethodSelectTemplate(station) : statusCellTemplate(getUpdatedStatus(station))}</td>
        <td><span class="completion-pill ${completionClass(getCompletenessAverage(station.code))}">${formatCompletenessAverage(station.code)}</span></td>
      </tr>
    `;
  }

  function transmissionIconTemplate(hasTransmission) {
    const state = hasTransmission ? "active" : "inactive";
    const label = hasTransmission ? "Con transmisión" : "Sin transmisión";
    return `<span class="transmission-icon ${state}" role="img" aria-label="${label}" title="${label}">
      <span class="font-icon" aria-hidden="true">&#xE704;</span>
    </span>`;
  }

  function renderHydrometMap(stations) {
    setVisibleBasins(filterStates.basin.selected);
    renderStationPoints(stations, selectedHydrometCode);
    const station = stations.find((item) => item.code === selectedHydrometCode);
    renderMapStationPopup(station);
  }

  function qcMethodSelectTemplate(station) {
    const method = getQcMethod(station.code);
    const options = qcOptions.map((option) =>
      `<option value="${option}"${option === method ? " selected" : ""}>${option}</option>`).join("");
    return `<span class="qc-method-editor">
      <button class="qc-method-value" type="button" data-qc-edit="${escapeHtml(station.code)}" aria-label="Editar método QC para ${escapeHtml(station.code)}">${method}</button>
      <select class="qc-method-select" data-qc-station="${escapeHtml(station.code)}" aria-label="Método QC para ${escapeHtml(station.code)}" hidden>${options}</select>
    </span>`;
  }

  function statusCellTemplate(value) {
    if (value !== "SI" && value !== "NO") return `<span class="status-cell empty">Sin registro</span>`;
    return `<span class="status-cell ${value === "SI" ? "yes" : "no"}">${value}</span>`;
  }

  function handleQcEditClick(event) {
    const button = event.target.closest("[data-qc-edit]");
    if (!button || selectedSource !== "quality") return;
    const editor = button.closest(".qc-method-editor");
    const select = editor.querySelector(".qc-method-select");
    button.hidden = true;
    select.hidden = false;
    select.focus();
  }

  function closeQcEditor(select) {
    const editor = select.closest(".qc-method-editor");
    const button = editor.querySelector(".qc-method-value");
    button.textContent = select.value;
    select.hidden = true;
    button.hidden = false;
  }

  function handleQcMethodBlur(event) {
    const select = event.target.closest("[data-qc-station]");
    if (select) closeQcEditor(select);
  }

  function handleQcMethodChange(event) {
    const select = event.target.closest("[data-qc-station]");
    if (!select) return;
    const code = select.dataset.qcStation;
    const method = qcOptions.includes(select.value) ? select.value : "None";
    if (method === "None") delete qcMethods[code];
    else qcMethods[code] = method;
    saveJson(qcStorageKey, qcMethods);
    renderHydrometMetrics(getFilteredHydrometStations());
    closeQcEditor(select);
  }

  function normalizeQcMethods(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    return Object.fromEntries(Object.entries(value).filter(([code, method]) => code && qcOptions.includes(method) && method !== "None"));
  }

  function getQcMethod(stationCode) {
    return qcOptions.includes(qcMethods[stationCode]) ? qcMethods[stationCode] : "None";
  }

  function renderMapStationPopup(station) {
    if (!station) {
      mapStationPopup.hidden = true;
      return;
    }

    const selectedVariables = filterStates.variable.selected;
    const record = completenessRecords[station.code];
    const variables = record && record.variables ? Object.entries(record.variables)
      .filter(([variable, value]) =>
        isAverageVariable(variable) &&
        Number.isFinite(Number(value)) &&
        (selectedVariables === null || selectedVariables.has(variable)))
      .map(([variable, value]) => ({ variable, value: clampPercentage(Number(value)) }))
      .sort((first, second) => first.variable.localeCompare(second.variable, "es")) : [];
    const completeness = variables.length
      ? variables.reduce((sum, item) => sum + item.value, 0) / variables.length
      : null;

    mapPopupStation.textContent = station.code;
    mapPopupMeta.textContent = [station.type, station.basin].filter(Boolean).join(" · ");
    if (selectedVariables === null) {
      mapPopupScope.textContent = "Todas las variables con registro";
    } else if (selectedVariables.size === 1) {
      mapPopupScope.textContent = `Filtro: ${[...selectedVariables][0]}`;
    } else {
      mapPopupScope.textContent = `${selectedVariables.size} variables filtradas`;
    }
    mapPopupCompleteness.textContent = completeness === null ? "Sin registro" : `${formatNumber(completeness)}%`;
    mapPopupProgress.style.width = `${completeness === null ? 0 : clampPercentage(completeness)}%`;
    mapPopupProgress.className = completeness === null ? "empty" : completionClass(completeness);
    mapPopupVariableCount.textContent = variables.length;
    mapPopupVariables.innerHTML = variables.length ? variables.map((item) => `
      <div class="map-variable-row">
        <span class="map-variable-icon ${completionClass(item.value)}" aria-hidden="true">
          <span class="font-icon">&#xE9D2;</span>
        </span>
        <div class="map-variable-main">
          <div>
            <strong>${escapeHtml(item.variable)}</strong>
            <span>${formatNumber(item.value)}%</span>
          </div>
          <div class="map-progress-track compact">
            <span class="${completionClass(item.value)}" style="width: ${clampPercentage(item.value)}%"></span>
          </div>
        </div>
      </div>
    `).join("") : `
      <div class="map-popup-empty">
        <span class="font-icon" aria-hidden="true">&#xE783;</span>
        <strong>Sin variables con registro</strong>
        <span>Esta estación todavía no tiene mediciones disponibles.</span>
      </div>
    `;
    mapStationPopup.hidden = false;
  }

  function renderHydrometMetrics(stations) {
    document.querySelector("#hydromet-total").textContent = stations.length;
    document.querySelector("#hydromet-basins").textContent = new Set(stations.map((station) => station.basin)).size;
    document.querySelector("#hydromet-status-count").textContent = selectedSource === "quality"
      ? stations.filter((station) => getQcMethod(station.code) !== "None").length
      : stations.filter((station) => getUpdatedStatus(station) === "SI").length;
    const typeCounts = stations.reduce((counts, station) => {
      const prefix = String(station.code || "").split("_")[0].toLowerCase();
      if (counts[prefix] !== undefined) counts[prefix] += 1;
      return counts;
    }, { met: 0, lim: 0, plu: 0, mli: 0, lpl: 0 });
    document.querySelector("#hydromet-map-total").textContent = stations.length;
    Object.entries(typeCounts).forEach(([type, count]) => {
      document.querySelector(`#hydromet-map-${type}`).textContent = count;
    });
  }

  function exportColumnDefinitions() {
    return [
      { key: "code", label: "Código", value: (station) => station.code },
      { key: "transmission", label: "Transmisión", value: (station) => station.transmission ? "Sí" : "No" },
      { key: "type", label: "Tipo", value: (station) => station.type },
      { key: "x", label: "X_UTM", value: (station) => station.x },
      { key: "y", label: "Y_UTM", value: (station) => station.y },
      { key: "z", label: "Z", value: (station) => station.z },
      { key: "basin", label: "Subcuenca", value: (station) => station.basin },
      { key: "start", label: "Primer registro", value: (station) => station.start || "Sin registro" },
      { key: "end", label: "Último registro", value: (station) => station.end || "Sin registro" },
      {
        key: "status",
        label: selectedSource === "quality" ? "QC" : "Actualizada",
        value: (station) => selectedSource === "quality" ? getQcMethod(station.code) : getUpdatedStatus(station) || "Sin registro"
      },
      { key: "completeness", label: "Completitud", value: (station) => getCompletenessAverage(station.code) }
    ];
  }

  function toggleExportPanel(event) {
    event.stopPropagation();
    const panel = document.querySelector("#hydromet-export-panel");
    const opening = panel.hidden;
    if (opening) renderExportOptions();
    panel.hidden = !opening;
    document.querySelector("#hydromet-export").setAttribute("aria-expanded", String(opening));
  }

  function closeExportPanel() {
    document.querySelector("#hydromet-export-panel").hidden = true;
    document.querySelector("#hydromet-export").setAttribute("aria-expanded", "false");
  }

  function renderExportOptions() {
    const columns = exportColumnDefinitions();
    document.querySelector("#hydromet-export-columns").innerHTML = columns.map((column) => `
      <label><input type="checkbox" value="${column.key}" checked><span>${column.label}</span></label>
    `).join("");
    const variables = [...new Set(getFilteredHydrometStations().flatMap(getVariablesForStation))]
      .filter(isAverageVariable).sort((a, b) => a.localeCompare(b, "es"));
    document.querySelector("#hydromet-export-variables").innerHTML = variables.map((variable) => `
      <label><input type="checkbox" value="${escapeHtml(variable)}" checked><span>${escapeHtml(variable)}</span></label>
    `).join("") || "<span>Sin variables disponibles</span>";
    document.querySelector("#hydromet-export-all").checked = true;
    document.querySelector("#hydromet-export-message").textContent = "";
    syncExportOptions();
  }

  function handleExportSelectAll(event) {
    document.querySelectorAll("#hydromet-export-columns input").forEach((input) => { input.checked = event.target.checked; });
    syncExportOptions();
  }

  function syncExportOptions() {
    const inputs = [...document.querySelectorAll("#hydromet-export-columns input")];
    document.querySelector("#hydromet-export-all").checked = inputs.every((input) => input.checked);
    document.querySelector("#hydromet-export-all").indeterminate = inputs.some((input) => input.checked) && inputs.some((input) => !input.checked);
    document.querySelector("#hydromet-export-completeness-options").hidden = !inputs.find((input) => input.value === "completeness")?.checked;
  }

  function handleCompletenessModeChange(event) {
    if (event.target.name !== "exportCompletenessMode") return;
    document.querySelector("#hydromet-export-variables").hidden = event.target.value !== "variables";
  }

  async function exportHydrometExcel() {
    const message = document.querySelector("#hydromet-export-message");
    const selectedKeys = [...document.querySelectorAll("#hydromet-export-columns input:checked")].map((input) => input.value);
    if (!selectedKeys.length) {
      message.textContent = "Selecciona al menos una columna.";
      return;
    }
    const definitions = new Map(exportColumnDefinitions().map((column) => [column.key, column]));
    const mode = document.querySelector('input[name="exportCompletenessMode"]:checked').value;
    const variables = mode === "variables"
      ? [...document.querySelectorAll("#hydromet-export-variables input:checked")].map((input) => input.value) : [];
    if (selectedKeys.includes("completeness") && mode === "variables" && !variables.length) {
      message.textContent = "Selecciona al menos una variable de completitud.";
      return;
    }

    const headers = [];
    selectedKeys.forEach((key) => {
      if (key === "completeness" && mode === "variables") variables.forEach((variable) => headers.push(`Completitud ${variable}`));
      else headers.push(definitions.get(key).label);
    });
    const rows = getFilteredHydrometStations().map((station) => selectedKeys.flatMap((key) => {
      if (key === "completeness" && mode === "variables") {
        return variables.map((variable) => getVariableCompleteness(station.code, variable));
      }
      return [definitions.get(key).value(station)];
    }));

    const button = document.querySelector("#hydromet-export-confirm");
    button.disabled = true;
    message.textContent = "Generando Excel…";
    try {
      const response = await fetch("/api/hydromet/export-excel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: `registro-hidromet-${new Date().toISOString().slice(0, 10)}`, headers, rows })
      });
      if (!response.ok) throw new Error((await response.json()).detail || "No fue posible generar el Excel");
      const result = await response.json();
      if (result.cancelled) {
        message.textContent = "Guardado cancelado.";
        return;
      }
      message.textContent = `Excel guardado: ${result.filename}`;
    } catch (error) {
      message.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  function getUpdatedStatus(station) {
    if (!station.end) return null;
    const endDate = new Date(`${station.end}T00:00:00`);
    if (Number.isNaN(endDate.getTime())) return null;
    const now = new Date();
    const firstDayOfCurrentMonth = new Date(now.getFullYear(), now.getMonth(), 1);
    return endDate >= firstDayOfCurrentMonth ? "SI" : "NO";
  }

  function getVariablesForStation(station) {
    if (Array.isArray(station.variables)) return station.variables;
    const serverVariables = completenessRecords[station.code] && completenessRecords[station.code].variables;
    return serverVariables ? Object.keys(serverVariables) : [];
  }

  function getCompletenessAverage(stationCode) {
    const record = completenessRecords[stationCode];
    if (!record || !record.variables) return null;
    const values = Object.entries(record.variables)
      .filter(([variable]) => isAverageVariable(variable))
      .map(([, value]) => Number(value))
      .filter((value) => Number.isFinite(value));
    if (values.length === 0) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  }

  function getFilteredVariableCompleteness(station) {
    const selected = filterStates.variable.selected;
    if (selected === null) return getCompletenessAverage(station.code);
    const stationVariables = new Set(getVariablesForStation(station));
    const values = [...selected]
      .filter((variable) => stationVariables.has(variable))
      .map((variable) => getVariableCompleteness(station.code, variable))
      .filter((value) => value !== null);
    if (values.length === 0) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  }

  function getVariableCompleteness(stationCode, variable) {
    const record = completenessRecords[stationCode];
    if (!record || !record.variables || record.variables[variable] === undefined) return null;
    const value = Number(record.variables[variable]);
    return Number.isFinite(value) ? clampPercentage(value) : null;
  }

  function isAverageVariable(variable) {
    return !averageExcludedVariables.has(variable);
  }

  function formatCompletenessAverage(stationCode) {
    const average = getCompletenessAverage(stationCode);
    return average === null ? "Sin registro" : `${formatNumber(average)}%`;
  }

  function completionClass(value) {
    if (!Number.isFinite(value)) return "empty";
    if (value >= 90) return "high";
    if (value >= 60) return "medium";
    return "low";
  }

  function clampPercentage(value) {
    if (!Number.isFinite(value)) return "";
    return Math.min(100, Math.max(0, value));
  }

  function formatNumber(value) {
    return Number(value.toFixed(2)).toString();
  }

  window.NotasHydromet = {
    initHydromet
  };
})();

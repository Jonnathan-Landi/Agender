(function () {
  const pathKeys = {
    "raw-data-path": "rawDataPath",
    "quality-data-path": "qualityDataPath"
  };
  const optionKeys = {
    "raw-include-subfolders": "rawIncludeSubfolders",
    "quality-include-subfolders": "qualityIncludeSubfolders"
  };
  const sourceKeys = {
    "raw-data-source": "rawDataSource",
    "quality-data-source": "qualityDataSource"
  };
  const oneDriveUrlKeys = {
    "raw-onedrive-url": "rawOneDriveUrl",
    "quality-onedrive-url": "qualityOneDriveUrl"
  };
  const activeCloudProvider = "onedrive";
  let cloudStatus = {};
  let cloudLoginPoll = null;
  let updateDownloadPhase = "idle";
  let updateDownloadPoll = null;
  let updateDownloadStartedAt = null;

  function initSettings() {
    renderAgenderAccount();
    document.querySelectorAll("[data-settings-page]").forEach((button) => {
      button.addEventListener("click", () => showPage(button.dataset.settingsPage));
    });

    document.querySelectorAll("[data-browse-path]").forEach((button) => {
      button.addEventListener("click", () => browsePath(button));
    });

    Object.keys(pathKeys).forEach((id) => {
      const input = document.querySelector(`#${id}`);
      input.addEventListener("change", saveTypedPaths);
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") { event.preventDefault(); input.blur(); }
      });
    });
    Object.keys(optionKeys).forEach((id) => {
      document.querySelector(`#${id}`).addEventListener("change", saveTypedPaths);
    });
    Object.keys(sourceKeys).forEach((id) => {
      document.querySelector(`#${id}`).addEventListener("change", async () => {
        renderPathSources();
        await saveTypedPaths();
      });
    });
    Object.keys(oneDriveUrlKeys).forEach((id) => {
      const input = document.querySelector(`#${id}`);
      input.addEventListener("change", saveTypedPaths);
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") { event.preventDefault(); input.blur(); }
      });
    });

    loadPaths();
    loadAppInfo();
    document.querySelector("#check-updates-button").addEventListener("click", checkForUpdates);
    document.querySelector("#install-update-button").addEventListener("click", handleUpdateAction);
    document.querySelector("#cloud-login-button").addEventListener("click", startCloudLogin);
    document.querySelector("#cloud-disconnect-button").addEventListener("click", disconnectCloud);
    window.addEventListener("agender:sync-status", handleSyncStatus);
    loadCloudStatus();
    restoreUpdateDownload();
  }

  function renderAgenderAccount() {
    const user = window.NotasLogin.getCurrentUser();
    document.querySelector("#settings-agender-username").textContent = user?.username || "Usuario";
    document.querySelector("#settings-agender-role").textContent =
      user?.role === "admin" ? "Administrador" : "Usuario con licencia";
  }

  async function loadAppInfo() {
    try {
      const response = await fetch("/api/app-info", { cache: "no-store" });
      const info = await readJsonResponse(response, "No fue posible leer la información de Agender.");
      document.querySelector("#about-product-name").textContent = info.name;
      document.querySelector("#about-version").textContent = info.version;
      document.querySelector("#update-current-version").textContent = info.version;
    } catch (error) {
      document.querySelector("#about-version").textContent = "No disponible";
    }
  }

  function tauriInvoke(command) {
    const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
    if (!invoke) throw new Error("La búsqueda de actualizaciones solo está disponible en la aplicación de escritorio.");
    return invoke(command);
  }

  async function checkForUpdates() {
    const button = document.querySelector("#check-updates-button");
    const available = document.querySelector("#update-available");
    const card = document.querySelector(".update-card");
    button.disabled = true;
    button.textContent = "Buscar actualizaciones";
    card.classList.remove("is-current");
    available.hidden = true;
    setUpdateMessage("Buscando actualizaciones...");
    try {
      const update = await tauriInvoke("check_for_update");
      const checkedAt = formatLastCheck(new Date());
      if (!update) {
        card.classList.add("is-current");
        document.querySelector("#update-title").textContent = "¡Todo está actualizado!";
        document.querySelector("#update-description").textContent = `Última comprobación: ${checkedAt}`;
        button.textContent = "Buscar de nuevo";
        setUpdateMessage("");
        return;
      }
      document.querySelector("#update-title").textContent = "Hay una actualización disponible";
      document.querySelector("#update-description").textContent = `Última comprobación: ${checkedAt}`;
      document.querySelector("#update-version").textContent = `Versión ${update.version}`;
      document.querySelector("#update-date").textContent = update.date ? new Date(update.date).toLocaleDateString("es-CO") : "";
      document.querySelector("#update-notes").textContent = update.body || "Incluye mejoras y correcciones para Agender.";
      available.hidden = false;
      setUpdateMessage("");
      await restoreUpdateDownload(update.version);
    } catch (error) {
      setUpdateMessage(typeof error === "string" ? error : error.message, true);
    } finally {
      button.disabled = false;
    }
  }

  function formatLastCheck(date) {
    return `hoy, ${date.toLocaleTimeString("es-CO", { hour: "numeric", minute: "2-digit" })}`;
  }

  function handleUpdateAction() {
    if (updateDownloadPhase === "ready") installUpdate();
    else downloadUpdate();
  }

  async function downloadUpdate() {
    const button = document.querySelector("#install-update-button");
    button.disabled = true;
    updateDownloadStartedAt = new Date();
    updateDownloadPhase = "downloading";
    renderUpdateDownload({ phase: "downloading", downloaded: 0, total: null, percent: null });
    startUpdateDownloadPoll();
    setUpdateMessage("Puedes continuar usando Agender mientras se descarga la actualización.");
    try {
      const status = await tauriInvoke("download_update");
      renderUpdateDownload(status);
    } catch (error) {
      setUpdateMessage(typeof error === "string" ? error : error.message, true);
      button.disabled = false;
      updateDownloadPhase = "failed";
      stopUpdateDownloadPoll();
    }
  }

  async function installUpdate() {
    const button = document.querySelector("#install-update-button");
    button.disabled = true;
    button.textContent = "Preparando actualización…";
    updateDownloadPhase = "installing";
    setUpdateMessage("Agender se cerrará, instalará la nueva versión en segundo plano y volverá a abrirse.");
    try {
      await tauriInvoke("install_update");
    } catch (error) {
      setUpdateMessage(typeof error === "string" ? error : error.message, true);
      button.disabled = false;
      button.textContent = "Reintentar instalación";
      updateDownloadPhase = "ready";
    }
  }

  async function restoreUpdateDownload(expectedVersion) {
    try {
      const status = await tauriInvoke("get_update_download_status");
      if (expectedVersion && status.version && status.version !== expectedVersion) return;
      renderUpdateDownload(status);
      if (status.phase === "downloading") {
        updateDownloadStartedAt ||= new Date();
        startUpdateDownloadPoll();
      }
    } catch {
      // El navegador de desarrollo no expone los comandos de actualización.
    }
  }

  function startUpdateDownloadPoll() {
    stopUpdateDownloadPoll();
    updateDownloadPoll = setInterval(async () => {
      try {
        renderUpdateDownload(await tauriInvoke("get_update_download_status"));
      } catch {
        stopUpdateDownloadPoll();
      }
    }, 250);
  }

  function stopUpdateDownloadPoll() {
    clearInterval(updateDownloadPoll);
    updateDownloadPoll = null;
  }

  function renderUpdateDownload(status) {
    updateDownloadPhase = status.phase || "idle";
    const panel = document.querySelector("#update-download-progress");
    const button = document.querySelector("#install-update-button");
    if (updateDownloadPhase === "idle") return;
    panel.hidden = false;

    const percent = updateDownloadPhase === "ready" ? 100 : Number(status.percent);
    const knownPercent = Number.isFinite(percent);
    const progress = knownPercent ? Math.min(100, Math.max(0, percent)) : 0;
    const track = panel.querySelector(".update-progress-track");
    document.querySelector("#update-progress-bar").style.width = `${progress}%`;
    track.setAttribute("aria-valuenow", String(progress));
    document.querySelector("#update-progress-detail").textContent = formatUpdateProgress(status, knownPercent ? progress : null);
    document.querySelector("#update-elapsed-time").textContent = `Tiempo transcurrido: ${formatElapsedTime()}`;

    if (updateDownloadPhase === "ready") {
      stopUpdateDownloadPoll();
      document.querySelector("#update-progress-label").textContent = "Actualización lista para instalar";
      button.textContent = "Reiniciar para actualizar";
      button.disabled = false;
      setUpdateMessage("La descarga terminó. Reinicia cuando estés listo; Agender se abrirá automáticamente al finalizar.");
    } else if (updateDownloadPhase === "downloading") {
      document.querySelector("#update-progress-label").textContent = "Descargando actualización…";
      button.textContent = "Descargando…";
      button.disabled = true;
    }
  }

  function formatUpdateProgress(status, percent) {
    const downloaded = formatBytes(Number(status.downloaded) || 0);
    const total = Number(status.total);
    if (Number.isFinite(total) && total > 0) return `${percent} % · ${downloaded} de ${formatBytes(total)}`;
    return downloaded;
  }

  function formatBytes(bytes) {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatElapsedTime() {
    const elapsed = updateDownloadStartedAt ? Math.max(0, Date.now() - updateDownloadStartedAt.getTime()) : 0;
    const totalSeconds = Math.floor(elapsed / 1000);
    return `${String(Math.floor(totalSeconds / 60)).padStart(2, "0")}:${String(totalSeconds % 60).padStart(2, "0")}`;
  }

  function setUpdateMessage(message, isError) {
    const element = document.querySelector("#update-message");
    element.textContent = message;
    element.classList.toggle("error", Boolean(isError));
  }

  async function loadCloudStatus() {
    try {
      const response = await fetch("/api/cloud/status", { cache: "no-store" });
      const result = await readJsonResponse(response, "No fue posible leer el estado de nube.");
      cloudStatus = result.providers || {};
      renderCloudProvider();
    } catch (error) {
      setBackupMessage(friendlyServerError(error), true);
    }
  }

  function renderCloudProvider() {
    const provider = cloudStatus.onedrive || {};
    const connected = document.querySelector("#onedrive-connected");
    const disconnected = document.querySelector("#onedrive-disconnected");
    connected.hidden = !provider.connected;
    disconnected.hidden = Boolean(provider.connected);
    if (!provider.connected) return;

    const account = provider.account || {};
    document.querySelector("#onedrive-account-name").textContent =
      account.displayName || account.email || "Cuenta Microsoft";
    document.querySelector("#onedrive-account-email").textContent =
      account.email && account.email !== account.displayName ? account.email : "";
    const status = document.querySelector("#onedrive-sync-status");
    if (provider.lastSyncError) {
      status.textContent = "Sincronización pendiente; Agender volverá a intentarlo automáticamente.";
    } else if (provider.lastSyncAt) {
      status.textContent = `Sincronización automática · Actualizado ${formatCloudDate(provider.lastSyncAt)}`;
    } else {
      status.textContent = "Sincronización automática activa";
    }
  }

  function handleSyncStatus(event) {
    const detail = event.detail || {};
    const status = document.querySelector("#onedrive-sync-status");
    if (!status) return;
    const labels = {
      disconnected: "OneDrive no está conectado.",
      disabled: "Preparando sincronización automática.",
      ready: "Sincronización automática activa.",
      syncing: "Sincronizando con OneDrive…",
      synced: `Sincronización automática${detail.result?.syncedAt ? ` · Actualizado ${formatCloudDate(detail.result.syncedAt)}` : " activa"}`,
      offline: "Sin conexión · Los cambios se sincronizarán automáticamente al regresar Internet.",
      error: "Sincronización pendiente; Agender volverá a intentarlo automáticamente."
    };
    status.textContent = labels[detail.state] || status.textContent;
  }

  async function startCloudLogin() {
    setBackupMessage("Abriendo inicio de sesión en el navegador...");
    try {
      const response = await fetch(`/api/cloud/${activeCloudProvider}/auth/start`, { method: "POST" });
      await readJsonResponse(response, "No fue posible iniciar sesión en la nube.");
      setBackupMessage("Completa el inicio de sesión en el navegador. Agender actualizará el estado en unos segundos.");
      clearTimeout(cloudLoginPoll);
      cloudLoginPoll = setTimeout(() => pollCloudLogin(0), 2500);
    } catch (error) {
      setBackupMessage(friendlyServerError(error), true);
    }
  }

  async function pollCloudLogin(attempt) {
    await loadCloudStatus();
    const selectedProvider = cloudStatus[activeCloudProvider] || {};
    if (selectedProvider.connected) {
      if (activeCloudProvider === "onedrive") {
        const provider = await window.NotasSync.refreshStatus();
        if (provider?.syncEnabled) {
          await window.NotasSync.syncNow({ quiet: true });
        }
      }
      return;
    }
    const delays = [4000, 6000, 10000, 15000, 20000, 30000];
    if (attempt < delays.length) {
      cloudLoginPoll = setTimeout(() => pollCloudLogin(attempt + 1), delays[attempt]);
    }
  }

  async function disconnectCloud() {
    setBackupMessage("Cerrando sesión de nube...");
    try {
      const response = await fetch(`/api/cloud/${activeCloudProvider}/disconnect`, { method: "POST" });
      await readJsonResponse(response, "No fue posible cerrar sesión.");
      setBackupMessage("Sesión de nube cerrada.");
      await loadCloudStatus();
    } catch (error) {
      setBackupMessage(friendlyServerError(error), true);
    }
  }

  function formatCloudDate(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });
  }

  function setBackupMessage(message, isError) {
    const element = document.querySelector("#backup-message");
    element.textContent = message;
    element.classList.toggle("error", Boolean(isError));
  }

  function showPage(page) {
    const navigationPage = ["about", "news"].includes(page) ? "information" : page;
    document.querySelectorAll(".settings-nav-item[data-settings-page]").forEach((button) => {
      button.classList.toggle("active", button.dataset.settingsPage === navigationPage);
    });
    document.querySelectorAll("[data-settings-panel]").forEach((panel) => {
      panel.classList.toggle("active", panel.dataset.settingsPanel === page);
    });
  }

  async function loadPaths() {
    try {
      const response = await fetch("/api/settings/paths", { cache: "no-store" });
      const paths = await readJsonResponse(response, "No fue posible cargar las rutas.");
      Object.entries(pathKeys).forEach(([id, key]) => { document.querySelector(`#${id}`).value = paths[key] || ""; });
      Object.entries(optionKeys).forEach(([id, key]) => { document.querySelector(`#${id}`).checked = paths[key] !== false; });
      Object.entries(sourceKeys).forEach(([id, key]) => { document.querySelector(`#${id}`).value = paths[key] || "local"; });
      Object.entries(oneDriveUrlKeys).forEach(([id, key]) => { document.querySelector(`#${id}`).value = paths[key] || ""; });
      renderPathSources();
    } catch (error) {
      setMessage(error.message, true);
    }
  }

  async function browsePath(button) {
    const input = document.querySelector(`#${button.dataset.browsePath}`);
    button.disabled = true;
    setMessage("Abriendo el selector de carpetas...");
    try {
      const response = await fetch("/api/select-directory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ initialPath: input.value })
      });
      const result = await readJsonResponse(response, "No fue posible abrir el selector de carpetas.");
      if (!result.path) return setMessage("");
      input.value = result.path;
      await savePaths();
      setMessage("Ruta guardada.");
    } catch (error) {
      setMessage(error.message, true);
    } finally {
      button.disabled = false;
    }
  }

  async function savePaths() {
    const payload = {};
    Object.entries(pathKeys).forEach(([id, key]) => { payload[key] = document.querySelector(`#${id}`).value; });
    Object.entries(optionKeys).forEach(([id, key]) => { payload[key] = document.querySelector(`#${id}`).checked; });
    Object.entries(sourceKeys).forEach(([id, key]) => { payload[key] = document.querySelector(`#${id}`).value; });
    Object.entries(oneDriveUrlKeys).forEach(([id, key]) => { payload[key] = document.querySelector(`#${id}`).value; });
    const response = await fetch("/api/settings/paths", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    await readJsonResponse(response, "No fue posible guardar las rutas.");
    window.dispatchEvent(new CustomEvent("agender:data-saved", {
      detail: { key: "agender.profile.onedrive-sources" }
    }));
  }

  function renderPathSources() {
    for (const source of ["raw", "quality"]) {
      const remote = document.querySelector(`#${source}-data-source`).value === "onedrive";
      document.querySelector(`[data-local-source="${source}"]`).hidden = remote;
      document.querySelector(`[data-onedrive-source="${source}"]`).hidden = !remote;
      document.querySelector(`[data-browse-path="${source}-data-path"]`).disabled = remote;
    }
  }

  async function saveTypedPaths() {
    try {
      await savePaths();
      setMessage("Rutas guardadas.");
    } catch (error) {
      setMessage(friendlyServerError(error), true);
    }
  }

  async function readJsonResponse(response, fallbackMessage) {
    const text = await response.text();
    let result = {};
    if (text) {
      try { result = JSON.parse(text); } catch { throw new Error(fallbackMessage); }
    }
    if (!response.ok || !text) throw new Error(result.error || result.detail || fallbackMessage);
    return result;
  }

  function friendlyServerError(error) {
    if (location.protocol === "file:" || /failed to fetch|cargar las rutas|selector de carpetas/i.test(error.message)) {
      return "Abre la aplicación desde http://localhost:3000 después de ejecutar python -m backend.";
    }
    return error.message;
  }

  function setMessage(message, isError) {
    const element = document.querySelector("#paths-settings-message");
    element.textContent = isError ? friendlyServerError(new Error(message)) : message;
    element.classList.toggle("error", Boolean(isError));
  }

  window.NotasSettings = { initSettings };
})();

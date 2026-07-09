(function () {
  const pathKeys = {
    "raw-data-path": "rawDataPath",
    "quality-data-path": "qualityDataPath"
  };
  const optionKeys = {
    "raw-include-subfolders": "rawIncludeSubfolders",
    "quality-include-subfolders": "qualityIncludeSubfolders"
  };
  let activeCloudProvider = "google";
  let cloudStatus = {};

  function initSettings() {
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

    loadPaths();
    loadAppInfo();
    document.querySelector("#check-updates-button").addEventListener("click", checkForUpdates);
    document.querySelector("#install-update-button").addEventListener("click", installUpdate);
    document.querySelector("#export-backup-button").addEventListener("click", exportBackup);
    document.querySelector("#import-backup-button").addEventListener("click", () => document.querySelector("#backup-file").click());
    document.querySelector("#backup-file").addEventListener("change", importBackup);
    document.querySelectorAll("[data-cloud-provider]").forEach((button) => {
      button.addEventListener("click", () => selectCloudProvider(button.dataset.cloudProvider));
    });
    document.querySelector("#save-cloud-client-button").addEventListener("click", saveCloudClient);
    document.querySelector("#cloud-login-button").addEventListener("click", startCloudLogin);
    document.querySelector("#cloud-disconnect-button").addEventListener("click", disconnectCloud);
    document.querySelector("#cloud-backup-button").addEventListener("click", createCloudBackup);
    document.querySelector("#cloud-restore-button").addEventListener("click", restoreCloudBackup);
    document.querySelector("#cloud-client-id").addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); saveCloudClient(); }
    });
    loadCloudStatus();
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
    } catch (error) {
      setUpdateMessage(typeof error === "string" ? error : error.message, true);
    } finally {
      button.disabled = false;
    }
  }

  function formatLastCheck(date) {
    return `hoy, ${date.toLocaleTimeString("es-CO", { hour: "numeric", minute: "2-digit" })}`;
  }

  async function installUpdate() {
    const button = document.querySelector("#install-update-button");
    button.disabled = true;
    setUpdateMessage("Descargando e instalando. Agender se reiniciará al terminar...");
    try {
      await tauriInvoke("install_update");
    } catch (error) {
      setUpdateMessage(typeof error === "string" ? error : error.message, true);
      button.disabled = false;
    }
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

  function selectCloudProvider(provider) {
    activeCloudProvider = provider;
    document.querySelectorAll("[data-cloud-provider]").forEach((button) => {
      const active = button.dataset.cloudProvider === provider;
      button.classList.toggle("active", active);
      button.setAttribute("aria-checked", String(active));
    });
    renderCloudProvider();
  }

  function renderCloudProvider() {
    const provider = cloudStatus[activeCloudProvider] || {};
    const account = document.querySelector("#cloud-account");
    const login = document.querySelector("#cloud-login-button");
    const disconnect = document.querySelector("#cloud-disconnect-button");
    document.querySelector("#cloud-client-id").value = provider.configured ? "••••••••••••••••" : "";
    document.querySelector("#cloud-redirect-uri").textContent = provider.redirectUri || "-";
    account.textContent = provider.connected
      ? `Conectado: ${(provider.account && (provider.account.displayName || provider.account.email)) || provider.label}`
      : provider.configured ? "Client ID guardado. Inicia sesión para activar la nube." : "Sin conexión. Pega el Client ID OAuth para comenzar.";
    if (provider.lastBackupAt) account.textContent += ` · Última copia: ${formatCloudDate(provider.lastBackupAt)}`;
    login.hidden = Boolean(provider.connected);
    disconnect.hidden = !provider.connected;
    document.querySelector("#cloud-backup-button").disabled = !provider.connected;
    document.querySelector("#cloud-restore-button").disabled = !provider.connected;
  }

  async function saveCloudClient() {
    const input = document.querySelector("#cloud-client-id");
    const clientId = input.value.trim();
    if (!clientId || clientId.includes("•")) {
      setBackupMessage("Pega un Client ID OAuth válido antes de guardar.", true);
      return;
    }
    setBackupMessage("Guardando Client ID...");
    try {
      const response = await fetch(`/api/cloud/${activeCloudProvider}/client`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clientId })
      });
      await readJsonResponse(response, "No fue posible guardar el Client ID.");
      setBackupMessage("Client ID guardado. Ahora puedes iniciar sesión.");
      await loadCloudStatus();
    } catch (error) {
      setBackupMessage(friendlyServerError(error), true);
    }
  }

  async function startCloudLogin() {
    setBackupMessage("Abriendo inicio de sesión en el navegador...");
    try {
      const response = await fetch(`/api/cloud/${activeCloudProvider}/auth/start`, { method: "POST" });
      const result = await readJsonResponse(response, "No fue posible iniciar sesión en la nube.");
      window.open(result.authUrl, "_blank", "noopener,noreferrer");
      setBackupMessage("Completa el inicio de sesión en el navegador. Agender actualizará el estado en unos segundos.");
      setTimeout(loadCloudStatus, 4000);
      setTimeout(loadCloudStatus, 9000);
    } catch (error) {
      setBackupMessage(friendlyServerError(error), true);
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

  async function createCloudBackup() {
    const button = document.querySelector("#cloud-backup-button");
    button.disabled = true;
    setBackupMessage("Subiendo copia de seguridad a la nube...");
    try {
      const response = await fetch(`/api/cloud/${activeCloudProvider}/backup`, { method: "POST" });
      const result = await readJsonResponse(response, "No fue posible crear la copia en la nube.");
      setBackupMessage(`Copia guardada en la nube: ${formatCloudDate(result.modifiedAt)}`);
      await loadCloudStatus();
    } catch (error) {
      setBackupMessage(friendlyServerError(error), true);
    } finally {
      renderCloudProvider();
    }
  }

  async function restoreCloudBackup() {
    if (!confirm("Restaurar la copia en nube reemplazará los datos actuales del usuario conectado. ¿Continuar?")) return;
    const button = document.querySelector("#cloud-restore-button");
    button.disabled = true;
    setBackupMessage("Restaurando copia desde la nube...");
    try {
      const response = await fetch(`/api/cloud/${activeCloudProvider}/restore`, { method: "POST" });
      const result = await readJsonResponse(response, "No fue posible restaurar la copia en la nube.");
      const restored = result.dataKeys ? result.dataKeys.length : 0;
      setBackupMessage(`Copia restaurada: configuración ${result.settings ? "sí" : "no"}, ${restored} grupos de datos. Recargando...`);
      setTimeout(() => location.reload(), 900);
    } catch (error) {
      setBackupMessage(friendlyServerError(error), true);
    } finally {
      renderCloudProvider();
    }
  }

  function formatCloudDate(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });
  }

  async function exportBackup() {
    const button = document.querySelector("#export-backup-button");
    button.disabled = true;
    setBackupMessage("Preparando copia de seguridad...");
    try {
      const response = await fetch("/api/backups/export", { cache: "no-store" });
      if (!response.ok) await readJsonResponse(response, "No fue posible crear la copia de seguridad.");
      const blob = await response.blob();
      const filename = filenameFromDisposition(response.headers.get("Content-Disposition")) || "agender-backup.agender-backup.json";
      const link = document.createElement("a");
      const url = URL.createObjectURL(blob);
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setBackupMessage("Copia descargada. Puedes guardarla en Google Drive, OneDrive o una memoria externa.");
    } catch (error) {
      setBackupMessage(friendlyServerError(error), true);
    } finally {
      button.disabled = false;
    }
  }

  async function importBackup(event) {
    const input = event.currentTarget;
    const file = input.files && input.files[0];
    if (!file) return;
    if (!confirm("Restaurar esta copia reemplazará los datos actuales del usuario conectado. ¿Continuar?")) {
      input.value = "";
      return;
    }
    const button = document.querySelector("#import-backup-button");
    button.disabled = true;
    setBackupMessage("Restaurando copia de seguridad...");
    try {
      const form = new FormData();
      form.append("backup", file);
      const response = await fetch("/api/backups/import", { method: "POST", body: form });
      const result = await readJsonResponse(response, "No fue posible restaurar la copia de seguridad.");
      const restored = result.dataKeys ? result.dataKeys.length : 0;
      setBackupMessage(`Copia restaurada: configuración ${result.settings ? "sí" : "no"}, ${restored} grupos de datos. Recargando...`);
      setTimeout(() => location.reload(), 900);
    } catch (error) {
      setBackupMessage(friendlyServerError(error), true);
    } finally {
      button.disabled = false;
      input.value = "";
    }
  }

  function filenameFromDisposition(value) {
    const match = /filename="([^"]+)"/i.exec(value || "");
    return match ? match[1] : "";
  }

  function setBackupMessage(message, isError) {
    const element = document.querySelector("#backup-message");
    element.textContent = message;
    element.classList.toggle("error", Boolean(isError));
  }

  function showPage(page) {
    document.querySelectorAll("[data-settings-page]").forEach((button) => {
      button.classList.toggle("active", button.dataset.settingsPage === page);
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
    const response = await fetch("/api/settings/paths", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    await readJsonResponse(response, "No fue posible guardar las rutas.");
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

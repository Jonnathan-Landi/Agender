(function () {
  const pathKeys = {
    "raw-data-path": "rawDataPath",
    "quality-data-path": "qualityDataPath"
  };
  const optionKeys = {
    "raw-include-subfolders": "rawIncludeSubfolders",
    "quality-include-subfolders": "qualityIncludeSubfolders"
  };

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
    button.disabled = true;
    available.hidden = true;
    setUpdateMessage("Buscando actualizaciones...");
    try {
      const update = await tauriInvoke("check_for_update");
      if (!update) {
        document.querySelector("#update-title").textContent = "Agender está actualizado";
        setUpdateMessage("No hay actualizaciones disponibles.");
        return;
      }
      document.querySelector("#update-title").textContent = "Hay una actualización disponible";
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

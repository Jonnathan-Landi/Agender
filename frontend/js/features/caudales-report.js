(function () {
  const PREFERENCES_KEY = "agender.reports.caudales.preferences";
  const REPORT_KEY = "agender.reports.caudales";
  let initialized = false;

  function init() {
    if (initialized) return;
    const frame = document.querySelector("#caudales-frame");
    const saveState = document.querySelector("#caudales-save-state");
    const settingsDialog = document.querySelector("#caudales-settings-dialog");
    const policySelect = document.querySelector("#caudales-policy-select");
    const editMode = document.querySelector("#caudales-edit-mode");
    const editInheritance = document.querySelector("#caudales-edit-inheritance");
    if (!frame) return;
    initialized = true;
    window.NotasCaudalesSession = {
      initialConfig: getInitialConfig(),
      initialPreferences: getInitialPreferences()
    };

    document.querySelector("#caudales-save").addEventListener("click", async () => {
      const bridge = getBridge(frame);
      if (!bridge) return;
      saveState.textContent = "Guardando…";
      const result = await bridge.save();
      if (!result?.ok) {
        saveState.textContent = result?.message || "No se pudo guardar";
        return;
      }
      await savePreferences(bridge.getSettings());
      window.NotasCaudalesSession.initialConfig = null;
      window.NotasCaudalesSession.initialPreferences = bridge.getSettings();
      saveState.textContent = "Guardado";
    });

    document.querySelector("#caudales-clear").addEventListener("click", () => {
      getBridge(frame)?.clear();
      saveState.textContent = "Cambios sin guardar";
    });

    document.querySelector("#caudales-settings").addEventListener("click", () => {
      syncSettings(frame, policySelect, editMode, editInheritance);
      settingsDialog.showModal();
    });
    document.querySelector("#caudales-settings-close").addEventListener("click", () => settingsDialog.close());
    document.querySelector("#caudales-settings-done").addEventListener("click", () => settingsDialog.close());
    settingsDialog.addEventListener("click", (event) => {
      if (event.target === settingsDialog) settingsDialog.close();
    });
    policySelect.addEventListener("change", () => {
      getBridge(frame)?.setPolicy(policySelect.value);
      saveState.textContent = policySelect.value === "it" ? "Política TI aplicada" : "Política por defecto aplicada";
    });
    editMode.addEventListener("change", () => {
      getBridge(frame)?.setEditMode(editMode.checked);
      syncSettings(frame, policySelect, editMode, editInheritance);
      saveState.textContent = editMode.checked ? "Modo edición activado" : "Modo edición desactivado";
    });
    editInheritance.addEventListener("change", () => {
      getBridge(frame)?.setEditInheritance(editInheritance.checked);
      syncSettings(frame, policySelect, editMode, editInheritance);
      saveState.textContent = editInheritance.checked ? "Herencia activada" : "Herencia desactivada";
    });

    document.querySelector("#caudales-print").addEventListener("click", async () => {
      const button = document.querySelector("#caudales-print");
      const reports = frame.contentDocument?.querySelector("#reports");
      if (!reports || button.disabled) return;
      button.disabled = true;
      saveState.textContent = "Preparando PDF…";
      try {
        const payload = getBridge(frame)?.getExportPayload();
        if (!payload?.reportsHtml) throw new Error("El reporte de Caudales todavía no está listo.");
        const response = await fetch("/api/reports/caudales/export-pdf", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const result = await readApiResult(response);
        if (!response.ok) throw new Error(result.detail || "No se pudo exportar el PDF.");
        saveState.textContent = result.canceled ? "Exportación cancelada" : result.message;
      } catch (error) {
        console.error(error);
        saveState.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    });

    frame.addEventListener("load", () => {
      window.setTimeout(() => {
        saveState.textContent = getBridge(frame) ? "Caudales cargado" : "No se pudo iniciar Caudales";
        syncSettings(frame, policySelect, editMode, editInheritance);
        syncFrameTheme(frame);
      }, 0);
    });
    window.addEventListener("message", (event) => {
      if (event.origin !== window.location.origin || event.source !== frame.contentWindow) return;
      if (event.data?.source !== "agender-wqreport") return;
      if (event.data.type === "ready" || event.data.type === "settings") {
        applySettings(event.data.settings, policySelect, editMode, editInheritance);
      } else if (event.data.type === "changed") {
        saveState.textContent = "Cambios sin guardar";
      } else if (event.data.type === "saved") {
        saveState.textContent = event.data.result?.ok ? "Guardado" : "No se pudo guardar";
      }
    });
    const themeObserver = new MutationObserver(() => syncFrameTheme(frame));
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    frame.src = frame.dataset.src;
  }

  function syncSettings(frame, policySelect, editMode, editInheritance) {
    applySettings(getBridge(frame)?.getSettings(), policySelect, editMode, editInheritance);
  }

  function applySettings(settings, policySelect, editMode, editInheritance) {
    if (!settings) return;
    policySelect.value = settings.policy;
    editMode.checked = settings.editMode;
    editInheritance.checked = settings.editInheritance;
    editInheritance.disabled = !settings.editInheritanceEnabled;
  }

  function getBridge(frame) {
    return frame.contentWindow?.WQReportBridge || null;
  }

  async function readApiResult(response) {
    const text = await response.text();
    if (!text) return {};
    try {
      return JSON.parse(text);
    } catch {
      return {
        detail: response.ok
          ? "El servidor devolvió una respuesta no válida."
          : "El servidor no pudo completar la exportación con el motor integrado."
      };
    }
  }

  function syncFrameTheme(frame) {
    const body = frame.contentDocument?.body;
    if (body) body.dataset.appTheme = document.documentElement.dataset.theme || "light";
  }

  function getInitialConfig() {
    const current = window.NotasStorage.loadJson(REPORT_KEY, null);
    if (current) return current;
    return null;
  }

  function getInitialPreferences() {
    const current = window.NotasStorage.loadJson(PREFERENCES_KEY, null);
    if (current) return current;
    return null;
  }

  function savePreferences(settings) {
    if (!settings) return;
    return window.NotasStorage.saveJson(PREFERENCES_KEY, {
      policy: settings.policy,
      editMode: Boolean(settings.editMode),
      editInheritance: Boolean(settings.editInheritance),
      editInheritanceEnabled: Boolean(settings.editInheritanceEnabled)
    }, { notify: false });
  }

  window.NotasCaudalesReport = { init };
})();

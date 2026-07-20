(function () {
  const PREFERENCES_KEY = "agender.reports.water-quality.preferences";
  const REPORT_KEY = "agender.reports.water-quality";
  let initialized = false;

  function init() {
    if (initialized) return;
    const frame = document.querySelector("#water-quality-frame");
    const saveState = document.querySelector("#water-quality-save-state");
    const settingsDialog = document.querySelector("#water-quality-settings-dialog");
    const policySelect = document.querySelector("#water-quality-policy-select");
    const editMode = document.querySelector("#water-quality-edit-mode");
    const editInheritance = document.querySelector("#water-quality-edit-inheritance");
    if (!frame) return;
    initialized = true;
    const legacyKeys = [];
    window.NotasWaterQualitySession = {
      initialConfig: getInitialConfig(legacyKeys),
      initialPreferences: getInitialPreferences(legacyKeys)
    };

    document.querySelector("#water-quality-save").addEventListener("click", async () => {
      const bridge = getBridge(frame);
      if (!bridge) return;
      saveState.textContent = "Guardando…";
      const result = await bridge.save();
      if (!result?.ok) {
        saveState.textContent = result?.message || "No se pudo guardar";
        return;
      }
      await savePreferences(bridge.getSettings());
      legacyKeys.forEach(key => localStorage.removeItem(key));
      window.NotasWaterQualitySession.initialConfig = null;
      window.NotasWaterQualitySession.initialPreferences = bridge.getSettings();
      saveState.textContent = "Guardado";
    });

    document.querySelector("#water-quality-clear").addEventListener("click", () => {
      getBridge(frame)?.clear();
      saveState.textContent = "Cambios sin guardar";
    });

    document.querySelector("#water-quality-settings").addEventListener("click", () => {
      syncSettings(frame, policySelect, editMode, editInheritance);
      settingsDialog.showModal();
    });
    document.querySelector("#water-quality-settings-close").addEventListener("click", () => settingsDialog.close());
    document.querySelector("#water-quality-settings-done").addEventListener("click", () => settingsDialog.close());
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

    document.querySelector("#water-quality-print").addEventListener("click", async () => {
      const button = document.querySelector("#water-quality-print");
      const reports = frame.contentDocument?.querySelector("#reports");
      if (!reports || button.disabled) return;
      button.disabled = true;
      saveState.textContent = "Preparando PDF…";
      try {
        const payload = getBridge(frame)?.getExportPayload();
        if (!payload?.reportsHtml) throw new Error("WQReport todavía no está listo.");
        const response = await fetch("/api/reports/water-quality/export-pdf", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const result = await response.json();
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
        saveState.textContent = getBridge(frame) ? "WQReport cargado" : "No se pudo iniciar WQReport";
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

  function syncFrameTheme(frame) {
    const body = frame.contentDocument?.body;
    if (body) body.dataset.appTheme = document.documentElement.dataset.theme || "light";
  }

  function getInitialConfig(legacyKeys) {
    const current = window.NotasStorage.loadJson(REPORT_KEY, null);
    if (current) return current;
    const user = localStorage.getItem("agender.auth.user") || "anonymous";
    const legacyKey = `user.${user}.reporte_calidad_agua_config_v8`;
    const raw = localStorage.getItem(legacyKey);
    if (!raw) return null;
    try {
      legacyKeys.push(legacyKey);
      return JSON.parse(raw);
    } catch (error) {
      console.error("No se pudo migrar la configuración anterior de WQReport.", error);
      return null;
    }
  }

  function getInitialPreferences(legacyKeys) {
    const current = window.NotasStorage.loadJson(PREFERENCES_KEY, null);
    if (current) return current;
    const user = localStorage.getItem("agender.auth.user") || "anonymous";
    const keys = [
      `user.${user}.wqreport_policy_profile`,
      `user.${user}.wqreport_edit_mode_enabled`,
      `user.${user}.wqreport_edit_inheritance_enabled`
    ];
    const [policy, editMode, editInheritance] = keys.map(key => localStorage.getItem(key));
    if (policy === null && editMode === null && editInheritance === null) return {};
    legacyKeys.push(...keys);
    return {
      policy: policy === "it" ? "it" : "default",
      editMode: editMode === "true",
      editInheritance: editMode === "true" && editInheritance === "true",
      editInheritanceEnabled: editMode === "true"
    };
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

  window.NotasWaterQualityReport = { init };
})();

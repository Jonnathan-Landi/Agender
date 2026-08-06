(async function () {
  function revealApplication() {
    const startup = document.querySelector("#startup-screen");
    if (!startup) return;
    startup.classList.add("is-complete");
    setTimeout(() => startup.remove(), 180);
  }
  setTimeout(revealApplication, 8000);

  function cacheBusted(source) {
    const separator = source.includes("?") ? "&" : "?";
    return `${source}${separator}recovery=${Date.now()}`;
  }

  function loadScriptOnce(source, forceReload = false) {
    const existing = document.querySelector(`script[data-agender-source="${source}"], script[src="${source}"]`);
    if (existing && !forceReload) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.dataset.agenderSource = source;
      script.src = forceReload ? cacheBusted(source) : source;
      script.onload = resolve;
      script.onerror = () => {
        script.remove();
        if (!forceReload) {
          loadScriptOnce(source, true).then(resolve, reject);
        } else {
          reject(new Error(`No fue posible cargar ${source}.`));
        }
      };
      document.head.appendChild(script);
    });
  }

  function loadStyleOnce(source) {
    const existing = document.querySelector(`link[rel="stylesheet"][href="${source}"]`);
    if (existing) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.dataset.agenderSource = source;
      link.href = source;
      link.onload = resolve;
      link.onerror = () => {
        link.remove();
        const retry = document.createElement("link");
        retry.rel = "stylesheet";
        retry.dataset.agenderSource = source;
        retry.href = cacheBusted(source);
        retry.onload = resolve;
        retry.onerror = () => {
          retry.remove();
          reject(new Error(`No fue posible cargar ${source}.`));
        };
        document.head.appendChild(retry);
      };
      document.head.appendChild(link);
    });
  }

  async function recoverMissingCoreScripts() {
    const coreScripts = [
      ["NotasStorage", "js/core/storage.js"],
      ["NotasSync", "js/core/sync.js"],
      ["NotasTheme", "js/core/theme.js"],
      ["NotasNavigation", "js/core/navigation.js"],
      ["NotasLogin", "js/core/login.js"]
    ];
    for (const [globalName, source] of coreScripts) {
      if (!window[globalName]) await loadScriptOnce(source, true);
    }
  }

  function showRecoveryWarning(errors) {
    if (!errors.length) return;
    const warning = document.createElement("div");
    warning.className = "startup-recovery-warning";
    warning.setAttribute("role", "alert");
    warning.innerHTML = "<strong>Algunos componentes no pudieron iniciarse.</strong><span>Cierra y abre Agender. Si continúa, reinstala la aplicación sin borrar tus documentos.</span>";
    document.body.appendChild(warning);
  }

  async function restoreBackgroundMode() {
    const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
    if (!invoke) return;
    try {
      const enabled = await invoke("get_background_mode");
      localStorage.setItem("agender.system.keep-running", String(Boolean(enabled)));
    } catch (error) {
      console.error("No fue posible restaurar el modo en segundo plano.", error);
    }
  }

  document.querySelectorAll("[data-dialog-close]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelector(`#${button.dataset.dialogClose}`).close();
    });
  });

  await recoverMissingCoreScripts();
  window.NotasTheme.initTheme();
  window.NotasNavigation.initNavigation();
  const authenticated = await window.NotasLogin.initLogin();
  if (!authenticated) {
    revealApplication();
    return;
  }
  await restoreBackgroundMode();
  await window.NotasStorage.init();
  const user = window.NotasLogin.getCurrentUser();
  const modules = new Set(user?.modules || []);
  const moduleLoads = [];
  if (user?.role === "admin") {
    moduleLoads.push(loadScriptOnce("js/core/license-admin.js"), loadStyleOnce("css/license-admin.css"));
  }
  if (modules.has("settings")) {
    moduleLoads.push(loadScriptOnce("js/core/settings.js"), loadStyleOnce("css/settings.css"));
  }
  if (modules.has("requests")) {
    moduleLoads.push(loadScriptOnce("js/features/requests.js"), loadStyleOnce("css/requests.css"));
  }
  if (modules.has("diary")) {
    moduleLoads.push(loadScriptOnce("js/features/diary.js"), loadStyleOnce("css/diary.css"));
  }
  if (modules.has("agenda")) {
    moduleLoads.push(loadScriptOnce("js/features/agenda.js"), loadStyleOnce("css/agenda.css"));
  }
  if (modules.has("report-water-quality")) {
    moduleLoads.push(
      loadScriptOnce("js/features/water-quality-report.js"),
      loadStyleOnce("css/water-quality-report.css")
    );
  }
  if (modules.has("report-hydromet-network")) {
    moduleLoads.push(
      loadScriptOnce("js/features/hydromet-design-export.js")
        .then(() => loadScriptOnce("js/features/hydromet-report.js")),
      loadStyleOnce("css/hydromet-report.css")
    );
  }
  if (modules.has("climatology")) {
    moduleLoads.push(
      loadScriptOnce("js/features/climatology.js"),
      loadStyleOnce("css/climatology.css")
    );
  }
  if (modules.has("hydromet")) {
    moduleLoads.push(
      loadScriptOnce("js/features/viewer.js"),
      loadScriptOnce("js/features/hydromet-map.js"),
      loadStyleOnce("css/hydromet.css")
    );
  }
  const moduleResults = await Promise.allSettled(moduleLoads);
  const moduleErrors = moduleResults.filter((result) => result.status === "rejected").map((result) => result.reason);
  if (modules.has("hydromet") && window.NotasHydrometMap) {
    try {
      await loadScriptOnce("js/features/hydromet.js");
    } catch (error) {
      moduleErrors.push(error);
    }
  }
  window.NotasTheme.applySavedTheme();
  if (user?.role === "admin") window.NotasLicenseAdmin?.init();
  if (modules.has("settings")) window.NotasSettings?.initSettings();
  if (modules.has("requests")) window.NotasRequests?.initRequests();
  if (modules.has("diary")) window.NotasDiary?.initDiary();
  if (modules.has("agenda")) window.NotasAgenda?.initAgenda();
  if (modules.has("report-water-quality") && window.NotasWaterQualityReport) {
    window.NotasWaterQualityReport.init();
  }
  if (modules.has("report-hydromet-network") && window.NotasHydrometReport) {
    window.NotasHydrometReport.init();
  }
  if (modules.has("climatology")) window.NotasClimatology?.init();
  if (modules.has("hydromet") && window.NotasViewer && window.NotasHydromet && window.NotasHydrometMap) {
    try {
      window.NotasViewer.initViewer();
      window.NotasHydromet.initHydromet();
      const loadMapData = async () => {
        await loadScriptOnce("js/subcuencas-data.js");
        window.NotasHydrometMap.refreshBasins();
      };
      if ("requestIdleCallback" in window) {
        window.requestIdleCallback(() => loadMapData().catch(console.error), { timeout: 3000 });
      } else {
        setTimeout(() => loadMapData().catch(console.error), 1500);
      }
    } catch (error) {
      console.error(error);
    }
  }
  window.NotasSync.start();
  window.NotasSync.bootstrap().catch((error) => console.error(error));
  showRecoveryWarning(moduleErrors);
  revealApplication();
})().catch((error) => {
  console.error("No fue posible iniciar Agender.", error);
  document.querySelector("#startup-screen")?.remove();
  const warning = document.createElement("div");
  warning.className = "startup-recovery-warning is-fatal";
  warning.setAttribute("role", "alert");
  warning.innerHTML = "<strong>Agender no pudo completar el inicio.</strong><span>Reabre la aplicación. Si el problema continúa, reinstálala; tus documentos no necesitan eliminarse.</span>";
  document.body.appendChild(warning);
});

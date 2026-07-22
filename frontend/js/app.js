(async function () {
  function revealApplication() {
    const startup = document.querySelector("#startup-screen");
    if (!startup) return;
    startup.classList.add("is-complete");
    setTimeout(() => startup.remove(), 180);
  }
  setTimeout(revealApplication, 8000);

  function loadScriptOnce(source) {
    const existing = document.querySelector(`script[src="${source}"]`);
    if (existing) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = source;
      script.onload = resolve;
      script.onerror = () => reject(new Error(`No fue posible cargar ${source}.`));
      document.head.appendChild(script);
    });
  }

  function loadStyleOnce(source) {
    const existing = document.querySelector(`link[rel="stylesheet"][href="${source}"]`);
    if (existing) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = source;
      link.onload = resolve;
      link.onerror = () => reject(new Error(`No fue posible cargar ${source}.`));
      document.head.appendChild(link);
    });
  }

  function restoreBackgroundMode() {
    const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
    if (!invoke) return;
    const enabled = localStorage.getItem("agender.system.keep-running") === "true";
    invoke("set_background_mode", { enabled }).catch(() => {});
  }

  document.querySelectorAll("[data-dialog-close]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelector(`#${button.dataset.dialogClose}`).close();
    });
  });

  window.NotasTheme.initTheme();
  window.NotasNavigation.initNavigation();
  const authenticated = await window.NotasLogin.initLogin();
  if (!authenticated) {
    revealApplication();
    return;
  }
  restoreBackgroundMode();
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
  if (modules.has("hydromet")) {
    moduleLoads.push(
      loadScriptOnce("js/features/viewer.js"),
      loadScriptOnce("js/features/hydromet-map.js"),
      loadStyleOnce("css/hydromet.css")
    );
  }
  await Promise.all(moduleLoads);
  if (modules.has("hydromet")) await loadScriptOnce("js/features/hydromet.js");
  window.NotasTheme.applySavedTheme();
  if (user?.role === "admin") window.NotasLicenseAdmin.init();
  if (modules.has("settings")) window.NotasSettings.initSettings();
  if (modules.has("requests")) window.NotasRequests.initRequests();
  if (modules.has("diary")) window.NotasDiary.initDiary();
  if (modules.has("agenda")) window.NotasAgenda.initAgenda();
  if (modules.has("report-water-quality")) {
    window.NotasWaterQualityReport.init();
  }
  if (modules.has("hydromet")) {
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
  revealApplication();
})();

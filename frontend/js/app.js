(async function () {
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

  document.querySelectorAll("[data-dialog-close]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelector(`#${button.dataset.dialogClose}`).close();
    });
  });

  window.NotasTheme.initTheme();
  window.NotasNavigation.initNavigation();
  const authenticated = await window.NotasLogin.initLogin();
  if (!authenticated) return;
  await window.NotasStorage.init();
  const user = window.NotasLogin.getCurrentUser();
  const modules = new Set(user?.modules || []);
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
      await loadScriptOnce("js/subcuencas-data.js");
      window.NotasViewer.initViewer();
      window.NotasHydromet.initHydromet();
    } catch (error) {
      console.error(error);
    }
  }
  window.NotasSync.start();
  window.NotasSync.bootstrap().catch((error) => console.error(error));
})();

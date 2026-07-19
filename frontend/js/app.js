(async function () {
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
  window.NotasTheme.applySavedTheme();
  window.NotasLicenseAdmin.init();
  window.NotasSettings.initSettings();
  window.NotasRequests.initRequests();
  window.NotasDiary.initDiary();
  window.NotasAgenda.initAgenda();
  window.NotasViewer.initViewer();
  window.NotasHydromet.initHydromet();
  window.NotasSync.start();
  window.NotasSync.bootstrap({ reloadOnRemote: true }).catch((error) => console.error(error));
})();

(function () {
  function init() {
    const form = document.querySelector("#license-admin-form");
    const authorityInput = document.querySelector("#license-authority-key");
    const authorityStatus = document.querySelector("#license-authority-status");
    const personalAll = document.querySelector("#license-personal-all");
    const personalModules = [...form.querySelectorAll('input[name="modules"][value="requests"], input[name="modules"][value="diary"], input[name="modules"][value="agenda"]')];
    const reportsAll = document.querySelector("#license-reports-all");
    const reportModules = [...form.querySelectorAll('input[name="modules"][value^="report-"]')];
    const syncPersonalGroup = setupPermissionGroup(personalAll, personalModules);
    const syncReportsGroup = setupPermissionGroup(reportsAll, reportModules);
    updateAuthorityStatus();
    authorityInput.addEventListener("change", async () => {
      const file = authorityInput.files?.[0];
      if (!file) return;
      const body = new FormData(); body.append("key", file);
      const response = await fetch("/api/licenses/import-authority", { method: "POST", body });
      if (!response.ok) {
        authorityStatus.textContent = (await response.json()).detail || "No fue posible importar la clave.";
        authorityStatus.classList.add("error");
        return;
      }
      document.body.dataset.authorityAvailable = "true";
      authorityInput.value = "";
      updateAuthorityStatus();
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const output = document.querySelector("#license-admin-message");
      output.classList.remove("error");
      if (document.body.dataset.authorityAvailable !== "true") {
        output.textContent = "Importa primero la clave privada de la autoridad.";
        output.classList.add("error");
        authorityInput.click();
        return;
      }
      const data = new FormData(form);
      const payload = { licenseId: data.get("licenseId"), fullName: data.get("fullName"), username: data.get("username"),
        temporaryPassword: data.get("temporaryPassword"), revision: Number(data.get("revision")), modules: data.getAll("modules") };
      const response = await fetch("/api/licenses/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!response.ok) {
        output.textContent = (await response.json()).detail;
        output.classList.add("error");
        return;
      }
      const blob = await response.blob(); const filename = `${payload.licenseId}.license.json`;
      if (window.showSaveFilePicker) {
        const handle = await window.showSaveFilePicker({ suggestedName: filename, types: [{ description: "Licencia Agender", accept: { "application/json": [".json"] } }] });
        const writable = await handle.createWritable(); await writable.write(blob); await writable.close();
        output.textContent = "Licencia guardada correctamente.";
      } else {
        const url = URL.createObjectURL(blob); const link = document.createElement("a");
        link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url);
        output.textContent = "Licencia guardada en la carpeta Descargas.";
      }
      form.reset();
      syncPersonalGroup();
      syncReportsGroup();
    });
    syncPersonalGroup();
    syncReportsGroup();

    function updateAuthorityStatus() {
      const available = document.body.dataset.authorityAvailable === "true";
      authorityStatus.textContent = available
        ? "Clave privada disponible. La aplicación puede emitir licencias firmadas."
        : "Importa la clave privada de la autoridad antes de generar una licencia.";
      authorityStatus.classList.toggle("error", !available);
    }
  }

  function setupPermissionGroup(group, children) {
    const synchronize = () => {
      const selected = children.filter((input) => input.checked).length;
      group.checked = selected === children.length;
      group.indeterminate = selected > 0 && selected < children.length;
    };
    group.addEventListener("change", () => {
      children.forEach((input) => { input.checked = group.checked; });
      synchronize();
    });
    children.forEach((input) => input.addEventListener("change", synchronize));
    return synchronize;
  }
  window.NotasLicenseAdmin = { init };
})();

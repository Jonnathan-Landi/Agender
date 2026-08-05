(function () {
  function init() {
    const form = document.querySelector("#license-admin-form");
    const authorityInput = document.querySelector("#license-authority-key");
    const previousLicenseInput = document.querySelector("#license-previous-file");
    const authorityStatus = document.querySelector("#license-authority-status");
    const output = document.querySelector("#license-admin-message");
    const personalAll = document.querySelector("#license-personal-all");
    const personalModules = [...form.querySelectorAll('input[name="modules"][value="requests"], input[name="modules"][value="diary"], input[name="modules"][value="agenda"]')];
    const reportsAll = document.querySelector("#license-reports-all");
    const reportModules = [...form.querySelectorAll('input[name="modules"][value^="report-"]')];
    const climateAll = document.querySelector("#license-climate-all");
    const climateModules = [...form.querySelectorAll('input[name="modules"][value="climatology"]')];
    const syncPersonalGroup = setupPermissionGroup(personalAll, personalModules);
    const syncReportsGroup = setupPermissionGroup(reportsAll, reportModules);
    const syncClimateGroup = setupPermissionGroup(climateAll, climateModules);
    updateAuthorityStatus();
    previousLicenseInput.addEventListener("change", async () => {
      const file = previousLicenseInput.files?.[0];
      if (!file) return;
      output.classList.remove("error");
      output.textContent = "Validando la licencia anterior…";
      const body = new FormData();
      body.append("license", file);
      try {
        const response = await fetch("/api/licenses/inspect", { method: "POST", body });
        const result = await response.json();
        if (!response.ok) {
          throw new Error(result.detail || "No fue posible importar la licencia.");
        }
        fillFromPreviousLicense(form, result);
        syncPersonalGroup();
        syncReportsGroup();
        syncClimateGroup();
        output.textContent = `Licencia válida importada. Se generará la revisión ${result.revision}; escribe una nueva clave temporal.`;
        form.elements.temporaryPassword.focus();
      } catch (error) {
        output.textContent = error.message || "No fue posible importar la licencia.";
        output.classList.add("error");
      } finally {
        previousLicenseInput.value = "";
      }
    });
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
      output.classList.remove("error");
      if (document.body.dataset.authorityAvailable !== "true") {
        output.textContent = "Importa primero la clave privada de la autoridad.";
        output.classList.add("error");
        authorityInput.click();
        return;
      }
      const data = new FormData(form);
      const revisionInput = form.elements.revision;
      if (Number(revisionInput.value) < Number(revisionInput.min || 1)) {
        output.textContent = `La revisión debe ser ${revisionInput.min} o superior.`;
        output.classList.add("error");
        revisionInput.focus();
        return;
      }
      const payload = { licenseId: data.get("licenseId"), fullName: data.get("fullName"), username: data.get("username"),
        temporaryPassword: data.get("temporaryPassword"), revision: Number(data.get("revision")),
        expiresAt: data.get("expiresAt") || null, modules: data.getAll("modules") };
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
      form.elements.revision.min = "1";
      syncPersonalGroup();
      syncReportsGroup();
      syncClimateGroup();
    });
    syncPersonalGroup();
    syncReportsGroup();
    syncClimateGroup();

    function updateAuthorityStatus() {
      const available = document.body.dataset.authorityAvailable === "true";
      authorityStatus.textContent = available
        ? "Clave privada disponible. La aplicación puede emitir licencias firmadas."
        : "Importa la clave privada de la autoridad antes de generar una licencia.";
      authorityStatus.classList.toggle("error", !available);
    }
  }

  function fillFromPreviousLicense(form, license) {
    form.elements.fullName.value = license.fullName || "";
    form.elements.username.value = license.username || "";
    form.elements.temporaryPassword.value = "";
    form.elements.licenseId.value = license.licenseId || "";
    form.elements.revision.value = String(license.revision || 1);
    form.elements.revision.min = String(license.revision || 1);
    form.elements.expiresAt.value = license.expiresAt ? String(license.expiresAt).slice(0, 10) : "";
    const selected = new Set(license.modules || []);
    form.querySelectorAll('input[name="modules"]').forEach((input) => {
      input.checked = selected.has(input.value);
    });
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

(function () {
  function init() {
    const open = document.querySelector("#license-admin-open");
    const dialog = document.querySelector("#license-admin-dialog");
    const form = document.querySelector("#license-admin-form");
    const authorityInput = document.querySelector("#license-authority-key");
    open.addEventListener("click", () => {
      if (document.body.dataset.authorityAvailable !== "true") authorityInput.click();
      else dialog.showModal();
    });
    authorityInput.addEventListener("change", async () => {
      const file = authorityInput.files?.[0];
      if (!file) return;
      const body = new FormData(); body.append("key", file);
      const response = await fetch("/api/licenses/import-authority", { method: "POST", body });
      if (!response.ok) { alert((await response.json()).detail || "No fue posible importar la clave"); return; }
      document.body.dataset.authorityAvailable = "true";
      authorityInput.value = "";
      dialog.showModal();
    });
    document.querySelector("#license-admin-close").addEventListener("click", () => dialog.close());
    document.querySelector("#license-admin-cancel").addEventListener("click", () => dialog.close());
    form.addEventListener("submit", async (event) => {
      event.preventDefault(); const data = new FormData(form);
      const payload = { licenseId: data.get("licenseId"), fullName: data.get("fullName"), username: data.get("username"),
        temporaryPassword: data.get("temporaryPassword"), modules: data.getAll("modules") };
      const output = document.querySelector("#license-admin-message");
      const response = await fetch("/api/licenses/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!response.ok) { output.textContent = (await response.json()).detail; return; }
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
    });
  }
  window.NotasLicenseAdmin = { init };
})();

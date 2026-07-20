(function () {
  const viewModules = {
    hydromet: "hydromet",
    requests: "requests",
    diary: "diary",
    agenda: "agenda",
    "report-water-quality": "report-water-quality",
    "report-hydromet-network": "report-hydromet-network",
    settings: "settings"
  };
  let currentUser = null;

  async function initLogin() {
    const dialog = document.querySelector("#login-dialog");
    const form = document.querySelector("#login-form");
    const username = document.querySelector("#login-username");
    const password = document.querySelector("#login-password");
    const toggle = document.querySelector("#login-toggle-password");
    const message = document.querySelector("#login-message");
    const licensePicker = document.querySelector("#license-picker");
    const licenseInput = document.querySelector("#login-license");
    const changeDialog = document.querySelector("#password-change-dialog");
    const licenseChangeDialog = document.querySelector("#license-change-dialog");
    const licenseChangeForm = document.querySelector("#license-change-form");
    const licenseChangeInput = document.querySelector("#license-change-file");
    const licenseChangeMessage = document.querySelector("#license-change-message");
    const licenseChangeLabel = licenseChangeInput.closest("label").querySelector("span:last-of-type");

    document.querySelector("#account-logout").addEventListener("click", async () => {
      await fetch("/api/auth/logout", { method: "POST" });
      localStorage.removeItem("agender.auth.user");
      location.reload();
    });
    document.querySelector("#account-license-change").addEventListener("click", () => {
      licenseChangeForm.reset();
      licenseChangeLabel.textContent = "Seleccionar nueva licencia";
      licenseChangeMessage.textContent = "";
      licenseChangeMessage.classList.remove("error");
      licenseChangeDialog.showModal();
    });
    const closeLicenseChange = () => licenseChangeDialog.close();
    document.querySelector("#license-change-close").addEventListener("click", closeLicenseChange);
    document.querySelector("#license-change-cancel").addEventListener("click", closeLicenseChange);
    licenseChangeDialog.addEventListener("click", (event) => {
      if (event.target === licenseChangeDialog) closeLicenseChange();
    });
    licenseChangeInput.addEventListener("change", () => {
      licenseChangeLabel.textContent = licenseChangeInput.files?.[0]?.name || "Seleccionar nueva licencia";
      licenseChangeMessage.textContent = "";
      licenseChangeMessage.classList.remove("error");
    });
    licenseChangeForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const file = licenseChangeInput.files?.[0];
      if (!file) {
        licenseChangeMessage.textContent = "Selecciona el archivo de la nueva licencia.";
        licenseChangeMessage.classList.add("error");
        return;
      }
      licenseChangeMessage.textContent = "Validando y aplicando licencia…";
      licenseChangeMessage.classList.remove("error");
      const body = new FormData();
      body.append("license", file);
      try {
        const response = await fetch("/api/auth/license", { method: "PUT", body });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || "No fue posible cambiar la licencia");
        licenseChangeMessage.textContent = "Licencia actualizada. Aplicando nuevos permisos…";
        window.setTimeout(() => location.reload(), 500);
      } catch (error) {
        licenseChangeMessage.textContent = error.message;
        licenseChangeMessage.classList.add("error");
      }
    });
    document.querySelector("#login-close").addEventListener("click", () => {
      if (currentUser) dialog.close();
    });
    document.querySelector("#login-cancel").addEventListener("click", () => {
      if (currentUser) dialog.close();
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog && currentUser) dialog.close();
    });
    dialog.addEventListener("cancel", (event) => {
      if (!currentUser) event.preventDefault();
    });
    toggle.addEventListener("click", () => {
      const visible = password.type === "text";
      password.type = visible ? "password" : "text";
      toggle.title = visible ? "Mostrar contraseña" : "Ocultar contraseña";
      toggle.setAttribute("aria-label", toggle.title);
      password.focus();
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      message.textContent = "Validando…";
      try {
        const response = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: username.value.trim(), password: password.value }) });
        const payload = await response.json();
        if (!response.ok) {
          licensePicker.hidden = false;
          throw new Error(`${payload.detail || "No fue posible iniciar sesión"}. Selecciona tu licencia para activar este equipo.`);
        }
        password.value = "";
        dialog.close();
        finishLogin(payload.user, changeDialog);
      } catch (error) {
        message.textContent = error.message;
        message.classList.add("error");
      }
    });
    licenseInput.addEventListener("change", async () => {
      const file = licenseInput.files?.[0];
      if (!file || !username.value || !password.value) return;
      message.textContent = "Validando licencia y credenciales…";
      const body = new FormData(); body.append("username", username.value.trim()); body.append("password", password.value); body.append("license", file);
      try {
        const response = await fetch("/api/auth/activate", { method: "POST", body });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || "No fue posible activar la licencia");
        clearUserStorage(payload.user.username);
        password.value = ""; dialog.close(); finishLogin(payload.user, changeDialog);
      } catch (error) { message.textContent = error.message; message.classList.add("error"); }
    });
    document.querySelector("#password-change-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const first = document.querySelector("#new-password").value;
      const second = document.querySelector("#confirm-password").value;
      const output = document.querySelector("#password-change-message");
      if (first !== second) { output.textContent = "Las contraseñas no coinciden."; return; }
      const response = await fetch("/api/auth/change-password", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: first }) });
      const payload = await response.json();
      if (!response.ok) { output.textContent = payload.detail; return; }
      changeDialog.close(); location.reload();
    });
    try {
      const response = await fetch("/api/auth/status", { cache: "no-store" });
      const status = await response.json();
      currentUser = status.user;
      applyAccess(status.user, status.license);
      document.querySelector("#login-close").hidden = !status.user;
      document.querySelector("#login-cancel").hidden = !status.user;
      document.querySelector("#license-admin-open").hidden = status.user?.role !== "admin";
      document.querySelector("#license-admin-view").hidden = status.user?.role !== "admin";
      document.body.dataset.authorityAvailable = String(Boolean(status.authorityAvailable));
      window.NotasNavigation.restoreActiveView();
      if (!status.user) dialog.showModal();
      if (status.user?.mustChangePassword) changeDialog.showModal();
      if (!status.license.valid) message.textContent = status.license.reason || "Se requiere una licencia válida.";
    } catch (error) {
      applyAccess(null, { valid: false });
    }
    delete document.documentElement.dataset.restoringView;
    return Boolean(currentUser);
  }

  function finishLogin(user, changeDialog) {
    localStorage.setItem("agender.auth.user", user.username);
    if (user.mustChangePassword) changeDialog.showModal();
    else location.reload();
  }

  function clearUserStorage(username) {
    const prefix = `user.${username}.`;
    Object.keys(localStorage).filter((key) => key.startsWith(prefix)).forEach((key) => localStorage.removeItem(key));
  }

  function applyAccess(user, license) {
    const modules = new Set(user?.modules || []);
    if (user) localStorage.setItem("agender.auth.user", user.username);
    document.body.dataset.modules = [...modules].join(" ");
    document.querySelector("#app-shell").classList.toggle("auth-locked", !user);
    Object.entries(viewModules).forEach(([view, module]) => {
      document.querySelectorAll(`.nav-item[data-view="${view}"], #${view}-view`).forEach((element) => {
        element.hidden = !modules.has(module);
      });
    });
    document.querySelectorAll("[data-nav-group]").forEach((group) => {
      const children = [...group.querySelectorAll(".nav-subitem[data-view]")];
      group.hidden = children.length > 0 && children.every((item) => item.hidden);
    });
    if (user) {
      const current = document.querySelector(".view.active");
      if (current?.hidden) document.querySelector(`.nav-item[data-view]:not([hidden])`)?.click();
    }
  }

  function getCurrentUser() {
    return currentUser;
  }

  window.NotasLogin = { initLogin, getCurrentUser };
})();

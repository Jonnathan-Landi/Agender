(function () {
  const viewModules = { hydromet: "hydromet", requests: "requests", diary: "diary", agenda: "agenda", settings: "settings" };

  async function initLogin() {
    let currentUser = null;
    const dialog = document.querySelector("#login-dialog");
    const form = document.querySelector("#login-form");
    const username = document.querySelector("#login-username");
    const password = document.querySelector("#login-password");
    const toggle = document.querySelector("#login-toggle-password");
    const message = document.querySelector("#login-message");
    const licensePicker = document.querySelector("#license-picker");
    const licenseInput = document.querySelector("#login-license");
    const changeDialog = document.querySelector("#password-change-dialog");
    const accountPopover = document.querySelector("#account-popover");

    document.querySelector("#login-open").addEventListener("click", () => {
      if (currentUser) {
        accountPopover.hidden = !accountPopover.hidden;
        return;
      }
      message.textContent = "";
      licensePicker.hidden = true;
      dialog.showModal();
      requestAnimationFrame(() => username.focus());
    });
    document.querySelector("#account-logout").addEventListener("click", async () => {
      await fetch("/api/auth/logout", { method: "POST" });
      localStorage.removeItem("agender.auth.user");
      location.reload();
    });
    document.addEventListener("pointerdown", (event) => {
      if (!accountPopover.hidden && !event.target.closest("#account-popover, #login-open")) accountPopover.hidden = true;
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") accountPopover.hidden = true;
    });
    document.querySelector("#login-close").addEventListener("click", () => dialog.close());
    document.querySelector("#login-cancel").addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
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
      document.querySelector("#license-admin-open").hidden = status.user?.role !== "admin";
      document.body.dataset.authorityAvailable = String(Boolean(status.authorityAvailable));
      if (!status.user && status.license.valid) dialog.showModal();
      if (status.user?.mustChangePassword) changeDialog.showModal();
      if (!status.license.valid) message.textContent = status.license.reason || "Se requiere una licencia válida.";
    } catch (error) {
      applyAccess(null, { valid: false });
    }
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
    const loginLabel = document.querySelector("#login-open .nav-label");
    loginLabel.textContent = user ? `${user.username} · Cerrar sesión` : "Iniciar sesión";
    if (user) {
      loginLabel.textContent = user.username;
      document.querySelector("#account-popover-name").textContent = user.username;
      document.querySelector("#account-popover-role").textContent = user.role === "admin" ? "Administrador" : "Usuario con licencia";
    }
    document.querySelector("#login-open").title = user ? `Sesión: ${user.username} (${user.role})` : "Iniciar sesión";
    if (user) {
      const current = document.querySelector(".view.active");
      if (current?.hidden) document.querySelector(`.nav-item[data-view]:not([hidden])`)?.click();
    }
  }

  window.NotasLogin = { initLogin };
})();

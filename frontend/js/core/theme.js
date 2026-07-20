(function () {
  const THEME_KEY = "agender.system.theme";
  const PROFILE_KEY = "agender.profile.preferences";
  const systemThemeQuery = window.matchMedia("(prefers-color-scheme: dark)");

  function initTheme() {
    applySavedTheme();
    window.addEventListener("agender:data-refreshed", (event) => {
      if (event.detail?.keys?.includes(PROFILE_KEY)) applySavedTheme();
    });

    document.querySelectorAll("[data-theme-option]").forEach((button) => {
      button.addEventListener("change", () => {
        if (button.type === "radio" && !button.checked) return;
        const theme = button.dataset.themeOption;
        localStorage.setItem(THEME_KEY, theme);
        window.NotasStorage?.updateJson(PROFILE_KEY, { theme });
        setTheme(theme);
      });
    });

    systemThemeQuery.addEventListener("change", () => {
      if ((localStorage.getItem(THEME_KEY) || "system") === "system") {
        setTheme("system");
      }
    });
  }

  function applySavedTheme() {
    const profileTheme = window.NotasStorage?.loadJson(PROFILE_KEY, {})?.theme;
    const theme = ["light", "dark", "system"].includes(profileTheme)
      ? profileTheme
      : localStorage.getItem(THEME_KEY) || "system";
    localStorage.setItem(THEME_KEY, theme);
    setTheme(theme);
  }

  function setTheme(theme) {
    const resolvedTheme = theme === "system" && systemThemeQuery.matches ? "dark" : theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = resolvedTheme;

    document.querySelectorAll("[data-theme-option]").forEach((button) => {
      button.classList.toggle("active", button.dataset.themeOption === theme);
      if (button.type === "radio") button.checked = button.dataset.themeOption === theme;
    });
  }

  window.NotasTheme = {
    initTheme,
    applySavedTheme
  };
})();

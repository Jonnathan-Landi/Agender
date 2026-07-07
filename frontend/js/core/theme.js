(function () {
  const THEME_KEY = "agender.system.theme";
  const systemThemeQuery = window.matchMedia("(prefers-color-scheme: dark)");

  function initTheme() {
    setTheme(localStorage.getItem(THEME_KEY) || "system");

    document.querySelectorAll("[data-theme-option]").forEach((button) => {
      button.addEventListener("click", () => {
        const theme = button.dataset.themeOption;
        localStorage.setItem(THEME_KEY, theme);
        setTheme(theme);
      });
    });

    systemThemeQuery.addEventListener("change", () => {
      if ((localStorage.getItem(THEME_KEY) || "system") === "system") {
        setTheme("system");
      }
    });
  }

  function setTheme(theme) {
    const resolvedTheme = theme === "system" && systemThemeQuery.matches ? "dark" : theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = resolvedTheme;

    document.querySelectorAll("[data-theme-option]").forEach((button) => {
      button.classList.toggle("active", button.dataset.themeOption === theme);
    });
  }

  window.NotasTheme = {
    initTheme
  };
})();

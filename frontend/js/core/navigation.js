(function () {
  const PANE_KEY = "agender.navigation.pane";

  function initNavigation() {
    const appShell = document.querySelector("#app-shell");
    const paneToggle = document.querySelector("#pane-toggle");
    const savedMode = localStorage.getItem(PANE_KEY);
    const startsCollapsed = savedMode ? savedMode === "collapsed" : window.matchMedia("(max-width: 900px)").matches;

    setPaneMode(appShell, paneToggle, startsCollapsed);

    paneToggle.addEventListener("click", () => {
      const shouldCollapse = appShell.classList.contains("nav-expanded");
      setPaneMode(appShell, paneToggle, shouldCollapse);
      localStorage.setItem(PANE_KEY, shouldCollapse ? "collapsed" : "expanded");
    });

    document.querySelectorAll("[data-view]").forEach((item) => {
      item.addEventListener("click", () => switchView(item.dataset.view));
    });
  }

  function setPaneMode(appShell, paneToggle, collapsed) {
    appShell.classList.toggle("nav-collapsed", collapsed);
    appShell.classList.toggle("nav-expanded", !collapsed);
    paneToggle.setAttribute("aria-expanded", String(!collapsed));
    paneToggle.setAttribute("aria-label", collapsed ? "Expandir navegacion" : "Contraer navegacion");
  }

  function switchView(viewName) {
    document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
    document.querySelector(`#${viewName}-view`).classList.add("active");

    document.querySelectorAll(".nav-item[data-view]").forEach((nav) => {
      nav.classList.toggle("active", nav.dataset.view === viewName);
    });
  }

  window.NotasNavigation = {
    initNavigation
  };
})();

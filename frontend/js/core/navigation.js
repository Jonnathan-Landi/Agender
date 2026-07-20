(function () {
  const PANE_KEY = "agender.navigation.pane";
  const GROUP_KEY_PREFIX = "agender.navigation.group.";
  const ACTIVE_VIEW_KEY = "agender.navigation.active-view";
  const viewScrollPositions = new Map();

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

    document.querySelectorAll("[data-nav-group]").forEach((group) => {
      const saved = localStorage.getItem(`${GROUP_KEY_PREFIX}${group.dataset.navGroup}`);
      setGroupExpanded(group, saved === null ? group.classList.contains("expanded") : saved === "expanded");
      group.querySelector(".nav-group-toggle").addEventListener("click", () => {
        if (appShell.classList.contains("nav-collapsed")) {
          setPaneMode(appShell, paneToggle, false);
          localStorage.setItem(PANE_KEY, "expanded");
        }
        const expanded = !group.classList.contains("expanded");
        setGroupExpanded(group, expanded);
        document.querySelectorAll(".nav-item.active").forEach((item) => item.classList.remove("active"));
        group.querySelector(".nav-group-toggle").classList.add("active");
        localStorage.setItem(`${GROUP_KEY_PREFIX}${group.dataset.navGroup}`, expanded ? "expanded" : "collapsed");
      });
    });

    document.querySelectorAll("[data-view]").forEach((item) => {
      item.addEventListener("click", () => switchView(item.dataset.view));
    });

    restoreActiveView();
  }

  function setGroupExpanded(group, expanded) {
    group.classList.toggle("expanded", expanded);
    group.querySelector(".nav-group-toggle").setAttribute("aria-expanded", String(expanded));
  }

  function setPaneMode(appShell, paneToggle, collapsed) {
    appShell.classList.toggle("nav-collapsed", collapsed);
    appShell.classList.toggle("nav-expanded", !collapsed);
    paneToggle.setAttribute("aria-expanded", String(!collapsed));
    paneToggle.setAttribute("aria-label", collapsed ? "Expandir navegacion" : "Contraer navegacion");
  }

  function switchView(viewName) {
    const target = document.querySelector(`#${viewName}-view`);
    if (!target) return;
    sessionStorage.setItem(ACTIVE_VIEW_KEY, viewName);
    const current = document.querySelector(".view.active");
    if (current === target) return;
    const workspace = document.querySelector(".workspace");
    if (current) {
      viewScrollPositions.set(current.id, workspace.scrollTop);
      current.classList.remove("active");
    }
    target.classList.add("active");

    document.querySelector(".nav-item[data-view].active")?.classList.remove("active");
    document.querySelector(`.nav-item[data-view="${viewName}"]`)?.classList.add("active");
    document.querySelector(".nav-group-toggle.active")?.classList.remove("active");
    document.querySelectorAll("[data-nav-group]").forEach((group) => {
      const containsActiveView = Boolean(group.querySelector(`.nav-item[data-view="${viewName}"]`));
      group.classList.toggle("has-active-child", containsActiveView);
      if (containsActiveView) setGroupExpanded(group, true);
    });
    workspace.scrollTop = viewScrollPositions.get(target.id) || 0;
  }

  function restoreActiveView() {
    const savedView = sessionStorage.getItem(ACTIVE_VIEW_KEY);
    const navigationItem = savedView
      ? document.querySelector(`.nav-item[data-view="${savedView}"]`)
      : null;
    if (navigationItem && !navigationItem.hidden) switchView(savedView);
  }

  window.NotasNavigation = {
    initNavigation,
    restoreActiveView
  };
})();

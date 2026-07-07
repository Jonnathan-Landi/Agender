(function () {
  let modal;
  let frame;
  let title;
  let contextMenu;

  function initViewer() {
    modal = document.querySelector("#station-viewer-modal");
    frame = document.querySelector("#station-viewer-frame");
    title = document.querySelector("#station-viewer-title");
    contextMenu = document.querySelector("#station-context-menu");
    document.querySelector("#station-viewer-close").addEventListener("click", closeViewer);
    modal.addEventListener("click", (event) => {
      if (event.target === modal) closeViewer();
    });
    contextMenu.addEventListener("click", (event) => {
      const action = event.target.closest("[data-viewer-action]");
      if (!action) return;
      openViewer(contextMenu.dataset.code, contextMenu.dataset.source);
    });
    document.addEventListener("pointerdown", (event) => {
      if (!event.target.closest("#station-context-menu")) hideContextMenu();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (!contextMenu.hidden) hideContextMenu();
      else if (!modal.hidden) closeViewer();
    });
    window.addEventListener("message", (event) => {
      if (event.origin === window.location.origin && event.data?.type === "agender:close-viewer") closeViewer();
    });
  }

  function showContextMenu(event, code, source) {
    if (!document.body.dataset.modules.split(" ").includes("viewer")) return;
    event.preventDefault();
    contextMenu.dataset.code = code;
    contextMenu.dataset.source = source;
    contextMenu.querySelector(".station-context-label").textContent = code;
    contextMenu.hidden = false;
    const bounds = contextMenu.getBoundingClientRect();
    contextMenu.style.left = `${Math.max(8, Math.min(event.clientX, innerWidth - bounds.width - 8))}px`;
    contextMenu.style.top = `${Math.max(8, Math.min(event.clientY, innerHeight - bounds.height - 8))}px`;
  }

  function hideContextMenu() {
    contextMenu.hidden = true;
  }

  function openViewer(code, source) {
    if (!code) return;
    hideContextMenu();
    title.textContent = `Viewer · ${code}`;
    frame.src = `/viewer/?station=${encodeURIComponent(code)}&source=${encodeURIComponent(source || "raw")}`;
    modal.hidden = false;
    document.body.classList.add("viewer-open");
    document.querySelector("#station-viewer-close").focus();
  }

  function closeViewer() {
    modal.hidden = true;
    frame.src = "about:blank";
    document.body.classList.remove("viewer-open");
  }

  window.NotasViewer = { initViewer, showContextMenu, openViewer };
})();

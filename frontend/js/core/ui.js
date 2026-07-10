(function () {
  function initDismissibleMenu({ menu, toggle, openClass = "open" }) {
    function close() {
      menu.classList.remove(openClass);
      toggle.setAttribute("aria-expanded", "false");
    }

    toggle.addEventListener("click", () => {
      const isOpen = menu.classList.toggle(openClass);
      toggle.setAttribute("aria-expanded", String(isOpen));
    });

    document.addEventListener("click", (event) => {
      if (!menu.contains(event.target)) close();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") close();
    });

    return { close };
  }

  window.NotasUI = { initDismissibleMenu };
})();

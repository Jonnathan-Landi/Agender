(function () {
  function csvEscape(value) {
    const text = String(value || "");
    return `"${text.replaceAll('"', '""')}"`;
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatDate(value) {
    if (!value) return "";
    const date = new Date(`${value}T00:00:00`);
    return new Intl.DateTimeFormat("es-CO", {
      year: "numeric",
      month: "long",
      day: "numeric"
    }).format(date);
  }

  window.NotasUtils = {
    csvEscape,
    escapeHtml,
    formatDate
  };
})();

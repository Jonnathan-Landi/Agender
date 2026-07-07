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

  function normalizeDate(value) {
    if (!value) return "";
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "";
    return parsed.toISOString().slice(0, 10);
  }

  function parseCsv(text) {
    const rows = [];
    let current = "";
    let row = [];
    let insideQuotes = false;

    for (let index = 0; index < text.length; index += 1) {
      const char = text[index];
      const next = text[index + 1];

      if (char === '"' && insideQuotes && next === '"') {
        current += '"';
        index += 1;
      } else if (char === '"') {
        insideQuotes = !insideQuotes;
      } else if (char === "," && !insideQuotes) {
        row.push(current);
        current = "";
      } else if ((char === "\n" || char === "\r") && !insideQuotes) {
        if (char === "\r" && next === "\n") index += 1;
        row.push(current);
        rows.push(row);
        row = [];
        current = "";
      } else {
        current += char;
      }
    }

    if (current || row.length) {
      row.push(current);
      rows.push(row);
    }
    return rows;
  }

  window.NotasUtils = {
    csvEscape,
    escapeHtml,
    formatDate,
    normalizeDate,
    parseCsv
  };
})();

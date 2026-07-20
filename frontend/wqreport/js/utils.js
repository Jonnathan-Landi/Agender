export function normalizeText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .trim();
}

export function extractNumericValue(text) {
  const match = String(text || "")
    .replace(",", ".")
    .match(/-?\d+(\.\d+)?/);

  return match ? Number(match[0]) : NaN;
}

export function formatDateLong(value) {
  if (!value) return "";

  const date = new Date(value);
  const day = date.getDate();
  const year = date.getFullYear();

  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");

  const monthNames = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
  ];

  const month = monthNames[date.getMonth()];

  return `${day} de ${month} de ${year} ${hours}:${minutes}`;
}

export function formatDateShort(value) {
  if (!value) return "";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "";
  }

  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const year = date.getFullYear();

  return `${day}/${month}/${year}`;
}

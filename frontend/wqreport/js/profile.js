// Both reports share the editor and page dimensions; their data stays separate.
export const isFlowReport = new URLSearchParams(window.location.search).get("report") === "caudales";
export const reportKey = isFlowReport ? "agender.reports.caudales" : "agender.reports.water-quality";
export const sessionKey = isFlowReport ? "NotasCaudalesSession" : "NotasWaterQualitySession";
export const basins = ["Yanuncay", "Tomebamba", "Machángara", "Tarqui"];

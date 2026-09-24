import { isFlowReport, reportKey } from "./profile.js";
export const totalPages = isFlowReport ? 2 : 4;

export const STORAGE_KEY = reportKey;

export const parameters = isFlowReport ? [["Caudal", "m³/s"], ["Lluvia", "mm"], ["Temperatura", "°C"]] : [
  ["Oxígeno disuelto", "mg/L"],
  ["Turbidez", "NTU"],
  ["Conductividad específica", "µS/cm"],
  ["pH", ""],
  ["ORP", "mV"],
  ["Materia orgánica disuelta", "RFU"],
  ["Temperatura del agua", "°C"],
  ["Carbono orgánico disuelto", "mg/L"],
  ["Sólidos suspendidos totales", "mg/L"],
  ["SAC 455", "1/m"],
  ["Color", "UC"],
  ["Hidrocarburos", "RFU"]
];

export const defaultParameterOrder = isFlowReport ? ["CAUDAL", "LLUVIA", "TEMPERATURA"] : [
  "OXIGENO DISUELTO",
  "TURBIDEZ",
  "CONDUCTIVIDAD ESPECIFICA",
  "PH",
  "ORP",
  "MATERIA ORGANICA DISUELTA",
  "TEMPERATURA DEL AGUA",
  "CARBONO ORGANICO DISUELTO",
  "SOLIDOS SUSPENDIDOS TOTALES",
  "SAC 455",
  "COLOR",
  "HIDROCARBUROS"
];

export const parameterUnits = isFlowReport ? { CAUDAL: "m³/s", LLUVIA: "mm", TEMPERATURA: "°C" } : {
  "OXIGENO DISUELTO": "mg/L",
  "TURBIDEZ": "NTU",
  "CONDUCTIVIDAD ESPECIFICA": "µS/cm",
  "PH": "",
  "ORP": "mV",
  "MATERIA ORGANICA DISUELTA": "RFU",
  "TEMPERATURA DEL AGUA": "°C",
  "CARBONO ORGANICO DISUELTO": "mg/L",
  "SOLIDOS SUSPENDIDOS TOTALES": "mg/L",
  "SAC 455": "1/m",
  "COLOR": "UC",
  "HIDROCARBUROS": "RFU"
};

export const graphs = isFlowReport ? [
  { iconClass: "icon-turbidez", icon: "≈", title: "CAUDALES (m³/s)", average: "Promedio:", paramKey: "CAUDAL", alt: "Gráfico de caudales" },
  { iconClass: "icon-sst", icon: "💧", title: "LLUVIA (mm)", average: "Promedio:", paramKey: "LLUVIA", alt: "Gráfico de lluvia" },
  { iconClass: "icon-color", icon: "🌡", title: "TEMPERATURA (°C)", average: "Promedio:", paramKey: "TEMPERATURA", alt: "Gráfico de temperatura" }
] : [
  {
    iconClass: "icon-turbidez",
    icon: "💧",
    title: "TURBIDEZ (NTU)",
    average: "Promedio:",
    paramKey: "TURBIDEZ",
    alt: "Gráfico de turbidez"
  },
  {
    iconClass: "icon-sst",
    icon: "≈",
    title: "SÓLIDOS SUSPENDIDOS TOTALES (mg/L)",
    average: "Promedio:",
    paramKey: "SOLIDOS SUSPENDIDOS TOTALES",
    alt: "Gráfico de sólidos suspendidos totales"
  },
  {
    iconClass: "icon-color",
    icon: "🎨",
    title: "COLOR (UC)",
    average: "Promedio:",
    paramKey: "COLOR",
    alt: "Gráfico de color"
  }
];

export const culebrillasVisibleParameters = [
  "OXIGENO DISUELTO",
  "TURBIDEZ",
  "CONDUCTIVIDAD ESPECIFICA",
  "PH",
  "ORP",
  "MATERIA ORGANICA DISUELTA",
  "TEMPERATURA DEL AGUA"
];

export const stationThresholds = {
  "TIXÁN": {
    "TURBIDEZ": 1500,
    "COLOR": 600
  },
  "TIXAN": {
    "TURBIDEZ": 1500,
    "COLOR": 600
  },
  "SUSTAG": {
    "TURBIDEZ": 150,
    "COLOR": 300
  },
  "CEBOLLAR": {
    "TURBIDEZ": 500,
    "COLOR": 500
  }
};

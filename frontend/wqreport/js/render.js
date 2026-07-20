import { totalPages, parameters, graphs } from "./data.js";
import { normalizeText } from "./utils.js";

export function createParameterRows() {
  return parameters.map(([name, value]) => {
    const paramKey = normalizeText(name);
    const needsFlag = paramKey === "TURBIDEZ" || paramKey === "COLOR";

    const labelHtml = needsFlag
      ? `<span class="param-label">${name}<span class="threshold-flag" title="Valor sobre umbral">⚑</span></span>`
      : name;

    return `
      <tr data-param-key="${paramKey}">
        <td class="parameter-name editable-text-target" data-edit-key="parameter-name:${paramKey}" contenteditable="true" spellcheck="false">${labelHtml}</td>
        <td class="parameter-value editable-text-target" data-edit-key="parameter-value:${paramKey}" contenteditable="true" spellcheck="false">${value}</td>
      </tr>
    `;
  }).join("");
}

export function createGraphCards() {
  return graphs.map(graph => `
    <div class="graph-card" data-param-key="${graph.paramKey}">
      <div class="graph-header">
        <div class="graph-title-wrap">
          <div class="metric-icon ${graph.iconClass}">${graph.icon}</div>
          <div class="graph-title editable editable-text-target" data-edit-key="graph-title:${graph.paramKey}" contenteditable="true">${graph.title}</div>
        </div>
        <div class="avg-box editable editable-text-target" data-edit-key="graph-average:${graph.paramKey}" contenteditable="false">${graph.average}</div>
      </div>
      <div class="graph-image-slot">
        <img class="graph-image is-missing" alt="${graph.alt}" tabindex="0">
        <div class="graph-image-upload-zone" tabindex="0">
          <label class="graph-image-upload-button">
            <input class="graph-image-input" type="file" accept="image/*">
            <span>Seleccionar archivo</span>
          </label>
          <span class="graph-image-upload-text">arrastre o pegue aqui</span>
        </div>
      </div>
    </div>
  `).join("");
}

export function createReportPage(pageNumber) {
  return `
    <section class="report-page">

      <div class="header-top">
        <img src="img/logo.png" alt="logo">
      </div>

      <div class="ti-report-header">
        <div class="ti-header-logo-cell">
          <img src="img/logo.png" alt="logo">
        </div>

        <div class="ti-header-title-cell">
          <div class="ti-header-title editable-text-target" data-edit-key="ti-header-title" contenteditable="true">REPORTE DIARIO DE CALIDAD DEL AGUA CRUDA</div>
        </div>

        <div class="ti-header-meta-cell">
          <div class="ti-header-meta-row">
            <strong>Fecha:</strong>
            <span class="ti-header-date-value"></span>
          </div>
          <div class="ti-header-meta-row">
            <strong>Versión:</strong>
            <span class="ti-header-version-value editable-text-target" data-edit-key="ti-header-version" contenteditable="true">1.0</span>
          </div>
          <div class="ti-header-meta-row ti-header-tlp-row">
            <strong>TLP:</strong>
            <select class="ti-header-tlp-select" aria-label="TLP">
              <option value="white" selected>BLANCO / Público</option>
              <option value="amber">AMBAR / Uso Interno</option>
              <option value="green">VERDE / Restringido</option>
              <option value="red">ROJO / Confidencial</option>
            </select>
          </div>
          <div class="ti-header-meta-row ti-header-page-value"></div>
        </div>
      </div>

      <div class="banner">
        <div class="banner-text">
          <h1 class="editable editable-text-target" data-edit-key="banner-title" contenteditable="true">REPORTE DIARIO DE CALIDAD DEL AGUA</h1>
          <p class="editable editable-text-target" data-edit-key="banner-subtitle" contenteditable="true">SISTEMA DE MONITOREO AUTOMÁTICO – ETAPA EP</p>
        </div>
      </div>

      <div class="cards">

        <div class="card">
          <div class="card-icon">📍</div>
          <div class="card-content">
            <div class="card-title editable-text-target" data-edit-key="station-label" contenteditable="true">ESTACIÓN</div>

            <select class="station-select">
              <option value="CEBOLLAR" selected>Cebollar</option>
              <option value="TIXÁN">Tixán</option>
              <option value="SUSTAG">Sustag</option>
              <option value="CULEBRILLAS">Culebrillas</option>
            </select>
          </div>
        </div>

        <div class="card">
          <div class="card-icon">≋</div>
          <div class="card-content">
            <div class="card-title editable-text-target" data-edit-key="type-label" contenteditable="true">TIPO</div>
            <div class="card-value editable editable-text-target" data-edit-key="type-value" contenteditable="true">Calidad del agua</div>
          </div>
        </div>

        <div class="card date-card">
          <button class="calendar-button" type="button" title="Seleccionar fecha y hora del reporte">
            📅
          </button>

          <div class="card-content">
            <div class="card-title editable-text-target" data-edit-key="date-label" contenteditable="true">FECHA DEL REPORTE</div>

            <input
              type="datetime-local"
              class="report-date-input"
              value="2026-06-01T08:00"
            >

            <div class="report-date-text editable-text-target" data-edit-key="date-text" contenteditable="true">
              1 de junio de 2026 08:00
            </div>
          </div>
        </div>

      </div>

      <div class="main">

        <div class="sidebar">
          <div class="panel">
            <div class="panel-header editable-text-target" data-edit-key="indicators-title" contenteditable="true">INDICADORES DEL DÍA</div>

            <div class="table-wrap">
              <table class="quality-table">
                <thead>
                  <tr>
                    <th class="editable-text-target" data-edit-key="table-header-name" contenteditable="true">Parámetro de medición</th>
                    <th class="editable-text-target" data-edit-key="table-header-value" contenteditable="true">Valor</th>
                  </tr>
                </thead>

                <tbody>
                  ${createParameterRows()}
                </tbody>
                <tfoot>
                  <tr>
                    <td colspan="2">
                      <button class="add-parameter-row-button" type="button" title="Agregar fila" aria-label="Agregar fila">
                        <span aria-hidden="true">+</span>
                      </button>
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>

          </div>

          <div class="blank-info-card hydrocarbon-note-card">
            <h3 class="blank-info-card-title">
              NOTAS
            </h3>

            <div class="blank-info-card-body">
              <ul class="note-list">
                <li>
                  En el sensor de hidrocarburos, valores mayores a
                  <strong>3000 RFU</strong> representan presencia de
                  <strong>películas aceitosas</strong> en el agua.
                </li>
                <li class="note-flag-line">
                  <span class="note-red-flag">⚑</span>
                  <span>= Parámetro fuera del rango de operatividad de la planta</span>
                </li>
              </ul>
            </div>
          </div>

        </div>

        <div class="graphs">
          ${createGraphCards()}
        </div>

      </div>

      <div class="obs">
        <h2 class="editable-text-target" data-edit-key="observations-title" contenteditable="true">OBSERVACIONES GENERALES</h2>
        <p class="editable editable-text-target" data-edit-key="observations-text" contenteditable="true">
          Todos los parametros se encuentran dentro de los limites de operatividad.
        </p>
      </div>

      <div class="footer editable editable-text-target" data-edit-key="footer" contenteditable="true">
        ETAPA EP – Departamento de Investigación y Monitoreo | Página ${pageNumber} de ${totalPages}
      </div>

    </section>
  `;
}

export function renderReports() {
  const reportsContainer = document.getElementById("reports");

  if (!reportsContainer) return;

  reportsContainer.innerHTML = "";

  for (let page = 1; page <= totalPages; page++) {
    reportsContainer.innerHTML += createReportPage(page);
  }
}

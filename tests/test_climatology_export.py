from pathlib import Path

import pytest

from backend import climatology_export


def test_safe_name_removes_windows_forbidden_characters():
    assert climatology_export._safe_name('Clima: Zona/"Urbana"?') == "Clima ZonaUrbana"
    assert climatology_export._safe_name("  ") == "Seguimiento_mensual_clima"


def test_document_contains_one_page_per_selected_report():
    pages = [
        {
            "territory": "Zona Urbana",
            "station": "MET_Ucubamba",
            "period": "julio 2026",
            "file": Path("temperatura.html").resolve().as_uri(),
        },
        {
            "territory": "Páramo",
            "station": "MET_Cancan",
            "period": "julio 2026",
            "file": Path("lluvia.html").resolve().as_uri(),
        },
        {
            "territory": "Seguimiento de Caudales",
            "station": "Cuatro cuencas",
            "period": "julio 2026",
            "file": Path("caudales.html").resolve().as_uri(),
        },
    ]

    document = climatology_export._document(pages)

    assert document.count('<section class="page">') == 3
    assert "SEGUIMIENTO TÉRMICO" in document
    assert "ESTACIÓN DE REFERENCIA: MET Ucubamba" in document
    assert "SEGUIMIENTO MENSUAL DEL CLIMA EN LA ZONA URBANA" in document
    assert "SEGUIMIENTO MENSUAL DEL CLIMA EN EL PÁRAMO" in document
    assert "SEGUIMIENTO DE CAUDALES" in document
    assert "LLUVIA VS CAUDAL · YANUNCAY · TOMEBAMBA · TARQUI · MACHÁNGARA" in document
    assert 'class="report-brand"' in document
    assert "<strong>ETAPA</strong><span>&#x276F;&#x276F;</span>" in document
    assert "color: white; background: #ff8500" in document
    assert "SEGUIMIENTO TÉRMICO Y DE PRECIPITACIONES" in document
    assert "grid-template-columns: 320px minmax(0, 1fr) 320px" in document
    assert ".heading { grid-column: 2; grid-row: 1; padding: 0; }" in document
    assert ".report-brand strong { font-size: 39.2px" in document
    assert "height: 146px" in document
    assert "height: calc(100% - 146px)" in document
    assert "padding: 22px 4px 19px" in document


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/reporte.html",
        "/api/climatology/report-file/not-a-job/reporte.html",
        "/api/climatology/report-file/0123456789abcdef0123456789abcdef/../../secreto.html",
    ],
)
def test_resolve_page_rejects_untrusted_report_urls(url):
    with pytest.raises(ValueError):
        climatology_export._resolve_page({"url": url})

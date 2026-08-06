from pathlib import Path

import pytest

from backend import climatology_export


def test_safe_name_removes_windows_forbidden_characters():
    assert climatology_export._safe_name('Clima: Zona/"Urbana"?') == "Clima ZonaUrbana"
    assert climatology_export._safe_name("  ") == "Seguimiento_mensual_clima"


def test_document_contains_one_page_per_selected_report():
    pages = [
        {
            "territory": "Zona urbana",
            "kind": "temperature",
            "station": "MET_Ucubamba",
            "period": "julio 2026",
            "file": Path("temperatura.html").resolve().as_uri(),
        },
        {
            "territory": "Zona urbana",
            "kind": "rain",
            "station": "PLU_Challuabamba",
            "period": "julio 2026",
            "file": Path("lluvia.html").resolve().as_uri(),
        },
    ]

    document = climatology_export._document(pages)

    assert document.count('<section class="page">') == 2
    assert "SEGUIMIENTO TÉRMICO" in document
    assert "SEGUIMIENTO DE PRECIPITACIONES" in document
    assert "ESTACIÓN DE REFERENCIA: MET Ucubamba" in document
    assert 'class="report-logo"' in document
    assert "wqreport/img/logo.png" in document
    assert "grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr)" in document
    assert ".heading { grid-column: 2; grid-row: 1; padding: 0; }" in document
    assert "max-width: calc(100% - 12px); max-height: 100px" in document


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

from __future__ import annotations

import html
import math
import shutil
from calendar import monthrange
from pathlib import Path
from typing import Any
from collections.abc import Callable

ASSET_ROOT = Path(__file__).resolve().parent / "data" / "climatology"
MONTHS = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)
MONTHS_SHORT = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")


def render_temperature(report: dict[str, Any], output: Path, year: int, month: int) -> Path:
    target = output / f"temperatura_{year:04d}_{month:02d}"
    plots = target / "plots"
    assets = target / "assets"
    plots.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ASSET_ROOT / "report.css", assets / "report.css")
    summary = report["summary"]
    period = f"{MONTHS[month - 1]} {year}"
    daily_calendar = _calendar_temperature_days(report["daily"], year, month)
    final_day = len(daily_calendar)
    daily_labels = [
        str(day) if day == 1 or day == final_day or (day % 3 == 0 and day <= final_day - 3) else ""
        for day in range(1, final_day + 1)
    ]
    historical = _merge_days(daily_calendar, report["historical"])
    _write_svg(
        plots / "01_comportamiento_diario.svg",
        _line_svg(
            daily_calendar,
            (("minimum", "#0867C8"), ("mean", "#1F2937"), ("maximum", "#EF2A26")),
            "Temperatura (°C)",
            x_labels=daily_labels,
            ribbon=("minimum", "maximum", "#EAF0F6"),
            canvas_width=900,
            canvas_height=400,
            font_size=22,
            max_ticks=20,
            x_label="Día del mes",
        ),
    )
    _write_svg(
        plots / "02_comparacion_mensual.svg",
        _line_svg(
            report["monthly"],
            (("maximum", "#EF2A26"), ("minimum", "#0867C8")),
            "Temperatura (°C)",
            x_labels=[MONTHS_SHORT[row["month"] - 1] for row in report["monthly"]],
            points=True,
            canvas_width=900,
            canvas_height=400,
            font_size=22,
            max_ticks=12,
            x_label="Mes",
            exact_range=True,
            range_padding=0.5,
            show_values=True,
            left_margin=138,
        ),
    )
    _write_svg(
        plots / "03_comparacion_historica.svg",
        _line_svg(
            historical,
            (
                ("minimumMean", "#0867C8", "4 4"),
                ("maximumMean", "#EF2A26", "4 4"),
                ("minimum", "#0867C8"),
                ("maximum", "#EF2A26"),
            ),
            "Temperatura (°C)",
            x_labels=daily_labels,
            ribbons=(("minimumP10", "minimumP90", "#CFE0F2"), ("maximumP10", "maximumP90", "#F8CACA")),
            canvas_width=900,
            canvas_height=400,
            font_size=22,
            max_ticks=20,
            x_label="Día del mes",
        ),
    )
    _write_svg(
        plots / "04_dia_mas_calido.svg",
        _line_svg(
            report["hottest"],
            (("value", "#EF2A26"),),
            "Temperatura (°C)",
            x_labels=_hourly_labels(report["hottest"]),
            area="#FFE1DD",
            canvas_width=1100,
            canvas_height=450,
            font_size=23,
            max_ticks=24,
            x_label="Hora del día",
            annotation_time=summary["hottestTime"],
            annotation_value=summary["hottestMaximum"],
        ),
    )
    comparison = _monthly_extremes_analysis(summary, month)
    historical_analysis = _historical_range_analysis(summary, month)
    hottest_analysis = _hottest_temperature_analysis(summary, month)
    document = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="assets/report.css"><title>Seguimiento térmico</title></head><body>
<main class="dashboard-shell">
  <section class="kpi-grid">
    {_temp_kpi(_fmt(summary["minimum"], " °C"), "MÍNIMA ABSOLUTA", period, "thermometer", "kpi-blue")}
    {_temp_kpi(_fmt(summary["mean"], " °C"), "TEMPERATURA MEDIA", period, "thermometer", "kpi-yellow")}
    {_temp_kpi(_fmt(summary["maximum"], " °C"), "MÁXIMA ABSOLUTA", period, "thermometer", "kpi-red")}
  </section>
  <section class="report-card card-daily">{_section("thermometer", f"Temperaturas diarias de {MONTHS[month - 1].lower()}", "", "blue", _legend())}<div class="plot-wrap plot-daily"><img class="plot-svg" src="plots/01_comportamiento_diario.svg"></div></section>
  <section class="middle-grid"><article class="report-card card-monthly">{_section("thermometer", f"Temperaturas mensuales durante {year}", comparison, "blue", _monthly_legend())}<div class="monthly-plot-zone"><img class="plot-svg" src="plots/02_comparacion_mensual.svg"></div></article>
  <article class="report-card card-history">{_section("chart", f"¿{MONTHS[month - 1]} estuvo dentro de lo habitual?", historical_analysis, "red")}<div class="plot-wrap plot-history"><img class="plot-svg" src="plots/03_comparacion_historica.svg"></div></article></section>
  <section class="report-card card-hot">{_section("flame", f"¿Qué día fue el más cálido de {MONTHS[month - 1].lower()}?", hottest_analysis, "orange")}<div class="plot-wrap plot-hot"><img class="plot-svg" src="plots/04_dia_mas_calido.svg"></div></section>
</main></body></html>"""
    report_file = target / "reporte_temperatura.html"
    report_file.write_text(document, encoding="utf-8")
    return report_file


def render_rain(report: dict[str, Any], output: Path, year: int, month: int) -> Path:
    target = output / f"lluvia_{year:04d}_{month:02d}"
    plots = target / "plots"
    assets = target / "assets"
    plots.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ASSET_ROOT / "rain_report.css", assets / "rain_report.css")
    summary = report["summary"]
    period = f"{MONTHS[month - 1]} {year}"
    annual = _merge_months(report["monthly"], report["monthlyHistorical"])
    monthly_rain = [row for row in report["monthly"] if row["month"] <= month]
    daily_rain = _calendar_rain_days(report["daily"], year, month)
    daily_comparison = _merge_rain_days(daily_rain, report["dailyHistorical"])
    final_day = len(daily_rain)
    daily_labels = [
        str(day) if day == 1 or day == final_day or (day % 3 == 0 and day <= final_day - 3) else ""
        for day in range(1, final_day + 1)
    ]
    _write_svg(
        plots / "01_lluvia_mensual.svg",
        _bar_svg(
            monthly_rain,
            "value",
            "#1970CE",
            "Precipitación mensual (mm)",
            x_labels=[MONTHS_SHORT[row["month"] - 1] for row in monthly_rain],
            canvas_width=1000,
            canvas_height=520,
            font_size=24,
            x_label="Mes",
        ),
    )
    history = [*report["history"], {"year": year, "value": summary["total"]}]
    _write_svg(
        plots / "02_historia_mensual.svg",
        _bar_svg(
            history,
            "value",
            "#87C7DF",
            "Precipitación mensual (mm)",
            highlight=len(history) - 1,
            reference=summary["historicalMean"],
            canvas_width=1000,
            canvas_height=500,
            font_size=24,
            x_label="Año",
        ),
    )
    _write_svg(
        plots / "03_comportamiento_mensual.svg",
        _bar_line_svg(
            daily_comparison,
            "rain",
            "mean",
            "#1970CE",
            "#466784",
            "Precipitación diaria (mm)",
            ribbons=("p10", "p90", "#CFE2FB"),
            x_labels=daily_labels,
            canvas_width=1000,
            canvas_height=430,
            font_size=24,
            max_ticks=20,
            x_label="Día del mes",
        ),
    )
    _write_svg(
        plots / "04_acumulado_anual.svg",
        _line_svg(
            annual,
            (("historical", "#8C99AA", "5 5"), ("current", "#0873DF")),
            "Acumulado (mm)",
            x_labels=MONTHS_SHORT,
            ribbons=(("p10", "p90", "#E1E5EA"),),
            canvas_width=1000,
            canvas_height=430,
            font_size=22,
            max_ticks=12,
            x_label="Mes",
            stretch=True,
            force_zero=True,
        ),
    )
    comparison = "Sin histórico" if summary["differencePercent"] is None else f"{summary['differencePercent']:+.0f}%"
    comparison_footer = (
        "No hay años comparables"
        if summary["difference"] is None
        else f"{summary['difference']:+.1f} mm respecto a lo habitual"
    )
    rainy_percent = round(summary["rainDays"] / summary["expectedDays"] * 100)
    rain_history_analysis = _rain_history_analysis(summary, month, year)
    below_average_analysis = _rain_days_below_average(daily_comparison)
    annual_rain_analysis = _annual_rain_analysis(annual)
    document = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="assets/rain_report.css"><title>Seguimiento de precipitaciones</title></head><body>
<main class="rain-shell">
  <section class="rain-kpi-grid">
    {_rain_kpi("rain", f"ACUMULADO {period.upper()}", _fmt(summary["total"], " mm"), "Lluvia total del mes", "blue")}
    {_rain_kpi("trend", "VS PROM. HISTÓRICO", comparison, comparison_footer, "green")}
    {_rain_kpi("calendar", "DÍAS CON LLUVIA", f"{summary['rainDays']} días", f"{rainy_percent}% del mes", "purple")}
    {_rain_kpi("drop", "MÁX. DIARIA", _fmt(summary["maximum"], " mm"), _date(summary["maximumDate"]), "cyan")}
  </section>
  <section class="rain-main-grid rain-overview-grid"><article class="rain-card rain-card-monthly"><h2>Lluvia mensual durante {year}</h2><div class="rain-chart rain-chart-main"><img class="rain-plot" src="plots/01_lluvia_mensual.svg"></div></article>
  <article class="rain-card rain-card-history"><h2>¿Cómo fue {MONTHS[month - 1].lower()} frente a otros años?</h2><p class="rain-subtitle">{rain_history_analysis}</p><div class="rain-chart rain-chart-main"><img class="rain-plot" src="plots/02_historia_mensual.svg"></div></article></section>
  <section class="rain-main-grid rain-comparison-grid"><article class="rain-card rain-card-evolution"><h2>¿Cómo evolucionó la lluvia durante {MONTHS[month - 1].lower()} de {year}?</h2><p class="rain-subtitle">{below_average_analysis}</p><div class="rain-legend"><span><i class="rain-swatch"></i>{MONTHS[month - 1]} {year}</span><span><i class="rain-line-dashed"></i>Promedio histórico</span><span><i class="rain-band"></i>Rango histórico (P10-P90)</span></div><div class="rain-chart rain-chart-comparison"><img class="rain-plot" src="plots/03_comportamiento_mensual.svg"></div></article>
  <article class="rain-card rain-card-annual"><h2>¿{year} está siendo más seco o más lluvioso de lo habitual?</h2><p class="rain-subtitle">{annual_rain_analysis}</p><div class="annual-summary"><span>A LA FECHA</span><strong>{_fmt(summary["annualTotal"], " mm")}</strong><small>Hist.: {_fmt(summary["annualHistoricalMean"], " mm")}</small></div><div class="rain-legend"><span><i class="rain-line-blue"></i>{year}</span><span><i class="rain-line-dashed"></i>Promedio histórico</span><span><i class="rain-band rain-band-gray"></i>Rango histórico (P10-P90)</span></div><div class="rain-chart rain-chart-comparison"><img class="rain-plot" src="plots/04_acumulado_anual.svg"></div></article></section>
</main></body></html>"""
    report_file = target / "reporte_lluvia.html"
    report_file.write_text(document, encoding="utf-8")
    return report_file


def _chart_frame(
    values: list[float],
    draw: Callable[[Callable[[int], float], Callable[[float], float], float], str],
    label: str,
    count: int,
    x_labels: list[str] | tuple[str, ...] | None = None,
    force_zero: bool = False,
    canvas_width: int = 900,
    canvas_height: int = 330,
    font_size: int = 12,
    max_ticks: int | None = None,
    x_label: str = "",
    exact_range: bool = False,
    range_padding: float = 0.0,
    left_margin: int | None = None,
    categorical_x: bool = False,
    stretch: bool = False,
) -> str:
    width, height = canvas_width, canvas_height
    left = left_margin or (112 if font_size >= 21 else (100 if font_size >= 18 else (88 if font_size >= 16 else 68)))
    right, top, bottom = 24, 28, height - (76 if x_label else 60)
    finite = [value for value in values if math.isfinite(value)] or [0.0, 1.0]
    low, high = min(finite), max(finite)
    if not exact_range:
        margin = max((high - low) * 0.12, 1.0)
        low = 0.0 if force_zero and low >= 0 else low - margin
        high += margin
    else:
        low -= range_padding
        high += range_padding

    def x(index):
        if categorical_x:
            return left + ((index + 0.5) / max(1, count)) * (width - left - right)
        return left + (index / max(1, count - 1)) * (width - left - right)

    def y(value):
        return bottom - ((value - low) / max(0.001, high - low)) * (bottom - top)

    grid = "".join(
        f'<line x1="{left}" y1="{top + i * (bottom - top) / 4:.1f}" x2="{width - right}" y2="{top + i * (bottom - top) / 4:.1f}" stroke="#E5EAF0"/><text class="axis-tick" x="{left - 11}" y="{top + i * (bottom - top) / 4 + 5:.1f}" text-anchor="end">{high - i * (high - low) / 4:.1f}</text>'
        for i in range(5)
    )
    labels = x_labels or [str(index + 1) for index in range(count)]
    if max_ticks is None:
        step = max(1, math.ceil(len(labels) / 12))
        tick_labels = [(index, value) for index, value in enumerate(labels) if index % step == 0]
    else:
        visible_labels = [(index, value) for index, value in enumerate(labels) if value]
        step = max(1, math.ceil(len(visible_labels) / max_ticks))
        tick_labels = [value for position, value in enumerate(visible_labels) if position % step == 0]
    ticks = "".join(
        f'<text class="axis-tick" x="{x(index):.1f}" y="{height - (42 if x_label else 25)}" text-anchor="middle">{_e(value)}</text>'
        for index, value in tick_labels
    )
    axis_center = (top + bottom) / 2
    x_title = (
        f'<text class="axis-title" x="{(left + width - right) / 2:.1f}" y="{height - 10}" text-anchor="middle">{_e(x_label)}</text>'
        if x_label
        else ""
    )
    aspect = ' preserveAspectRatio="none"' if stretch else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"{aspect}><style>text{{font:{font_size}px Segoe UI,Arial;fill:#334155}}.axis-tick{{font-weight:650}}.axis-title{{font-size:{font_size + 2}px;font-weight:750}}.value-label{{font-size:17px;font-weight:750;paint-order:stroke;stroke:#fff;stroke-width:4px;stroke-linejoin:round}}.peak-label{{font-size:{font_size + 5}px;font-weight:800;paint-order:stroke;stroke:#fff;stroke-width:6px;stroke-linejoin:round}}line{{shape-rendering:crispEdges}}</style>{grid}<text class="axis-title" x="{-axis_center:.1f}" y="24" text-anchor="middle" transform="rotate(-90)">{_e(label)}</text>{draw(x, y, bottom)}{ticks}{x_title}</svg>'


def _line_svg(
    rows: list[dict[str, Any]],
    series: tuple[tuple[str, str] | tuple[str, str, str], ...],
    label: str,
    x_labels=None,
    points=False,
    ribbon=None,
    ribbons=(),
    area=None,
    canvas_width=900,
    canvas_height=330,
    font_size=12,
    max_ticks=None,
    x_label="",
    exact_range=False,
    range_padding=0.0,
    show_values=False,
    left_margin=None,
    annotation_time=None,
    annotation_value=None,
    stretch=False,
    force_zero=False,
) -> str:
    values = [_num(row.get(key)) for row in rows for key, *_rest in series]
    for lower, upper, _colour in ribbons:
        values.extend(_num(row.get(lower)) for row in rows)
        values.extend(_num(row.get(upper)) for row in rows)

    def draw(x, y, bottom):
        parts = []
        ribbon_specs = list(ribbons) + ([ribbon] if ribbon else [])
        for lower, upper, colour in ribbon_specs:
            top_points = [(x(i), y(_num(row.get(upper)))) for i, row in enumerate(rows) if _finite(row.get(upper))]
            low_points = [
                (x(i), y(_num(row.get(lower)))) for i, row in reversed(list(enumerate(rows))) if _finite(row.get(lower))
            ]
            if top_points and low_points:
                parts.append(f'<polygon points="{_points(top_points + low_points)}" fill="{colour}" opacity=".62"/>')
        if area and series:
            key = series[0][0]
            pts = [(x(i), y(_num(row.get(key)))) for i, row in enumerate(rows) if _finite(row.get(key))]
            if pts:
                parts.append(
                    f'<polygon points="{_points([(pts[0][0], bottom), *pts, (pts[-1][0], bottom)])}" fill="{area}" opacity=".55"/>'
                )
        for spec in series:
            key, colour, *dash = spec
            pts = [(x(i), y(_num(row.get(key)))) for i, row in enumerate(rows) if _finite(row.get(key))]
            if pts:
                parts.append(
                    f'<polyline points="{_points(pts)}" fill="none" stroke="{colour}" stroke-width="2.5" stroke-dasharray="{dash[0] if dash else "none"}" stroke-linejoin="round"/>'
                )
            if points:
                parts.extend(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{colour}"/>' for px, py in pts)
            if show_values:
                for i, row in enumerate(rows):
                    if not _finite(row.get(key)):
                        continue
                    move_first_maximum = i == 0 and key == "maximum"
                    label_x = x(i) + 12 if move_first_maximum else x(i)
                    label_anchor = "start" if move_first_maximum else "middle"
                    parts.append(
                        f'<text class="value-label" x="{label_x:.1f}" y="{y(_num(row.get(key))) - 11:.1f}" text-anchor="{label_anchor}" fill="{colour}">{_num(row.get(key)):.1f}°</text>'
                    )
            if annotation_time and annotation_value is not None and pts:
                annotation_index = next(
                    (
                        i
                        for i, row in enumerate(rows)
                        if str(row.get("time", "")) == str(annotation_time) and _finite(row.get(key))
                    ),
                    None,
                )
                if annotation_index is None:
                    continue
                peak_x = x(annotation_index)
                peak_y = y(_num(rows[annotation_index].get(key)))
                direction = -1 if peak_x > canvas_width * 0.72 else 1
                label_x = peak_x + direction * 82
                label_y = peak_y - 38
                line_start_x = label_x - direction * 25
                parts.append(
                    '<defs><marker id="peak-arrow" markerWidth="9" markerHeight="9" '
                    'refX="7" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 Z" '
                    f'fill="{colour}"/></marker></defs>'
                    f'<line x1="{line_start_x:.1f}" y1="{label_y + 7:.1f}" '
                    f'x2="{peak_x + direction * 5:.1f}" y2="{peak_y - 4:.1f}" stroke="{colour}" '
                    'stroke-width="2.5" marker-end="url(#peak-arrow)"/>'
                    f'<circle cx="{peak_x:.1f}" cy="{peak_y:.1f}" r="4.5" fill="{colour}"/>'
                    f'<text class="peak-label" x="{label_x:.1f}" y="{label_y:.1f}" '
                    f'text-anchor="middle" fill="{colour}">{_num(annotation_value):.1f} °C</text>'
                )
        return "".join(parts)

    return _chart_frame(
        [value for value in values if math.isfinite(value)],
        draw,
        label,
        len(rows),
        x_labels,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        font_size=font_size,
        max_ticks=max_ticks,
        x_label=x_label,
        exact_range=exact_range,
        range_padding=range_padding,
        left_margin=left_margin,
        stretch=stretch,
        force_zero=force_zero,
    )


def _bar_svg(
    rows,
    key,
    colour,
    label,
    x_labels=None,
    highlight=None,
    reference=None,
    canvas_width=900,
    canvas_height=330,
    font_size=12,
    x_label="",
):
    values = [_num(row.get(key)) for row in rows]

    def draw(x, y, bottom):
        bar_width = max(8, (canvas_width - 130) / max(1, len(rows)) * 0.62)
        bars = "".join(
            f'<rect x="{x(i) - bar_width / 2:.1f}" y="{y(value):.1f}" width="{bar_width:.1f}" height="{max(1, bottom - y(value)):.1f}" fill="{("#146FC4" if highlight == i else colour)}"/>'
            for i, value in enumerate(values)
            if math.isfinite(value)
        )
        line = (
            f'<line x1="{x(0):.1f}" y1="{y(reference):.1f}" x2="{x(max(0, len(rows) - 1)):.1f}" y2="{y(reference):.1f}" stroke="#254D7E" stroke-width="2" stroke-dasharray="7 5"/>'
            if _finite(reference)
            else ""
        )
        return bars + line

    labels = x_labels or [str(row.get("year", index + 1)) for index, row in enumerate(rows)]
    return _chart_frame(
        [*values, _num(reference)],
        draw,
        label,
        len(rows),
        labels,
        force_zero=True,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        font_size=font_size,
        x_label=x_label,
        categorical_x=True,
        stretch=True,
    )


def _bar_line_svg(
    rows,
    bar_key,
    line_key,
    bar_colour,
    line_colour,
    label,
    ribbons=None,
    x_labels=None,
    canvas_width=900,
    canvas_height=330,
    font_size=12,
    max_ticks=None,
    x_label="",
):
    values = [_num(row.get(key)) for row in rows for key in (bar_key, line_key)]
    if ribbons:
        lower, upper, _colour = ribbons
        values.extend(_num(row.get(key)) for row in rows for key in (lower, upper))

    def draw(x, y, bottom):
        ribbon_shape = ""
        if ribbons:
            lower, upper, ribbon_colour = ribbons
            upper_points = [(x(i), y(_num(row.get(upper)))) for i, row in enumerate(rows) if _finite(row.get(upper))]
            lower_points = [
                (x(i), y(_num(row.get(lower)))) for i, row in reversed(list(enumerate(rows))) if _finite(row.get(lower))
            ]
            if upper_points and lower_points:
                ribbon_shape = (
                    f'<polygon points="{_points(upper_points + lower_points)}" fill="{ribbon_colour}" opacity=".72"/>'
                )
        width = max(7, (canvas_width - 130) / max(1, len(rows)) * 0.48)
        bars = "".join(
            f'<rect x="{x(i) - width / 2:.1f}" y="{y(_num(row.get(bar_key))):.1f}" width="{width:.1f}" height="{max(1, bottom - y(_num(row.get(bar_key)))):.1f}" fill="{bar_colour}"/>'
            for i, row in enumerate(rows)
            if _finite(row.get(bar_key))
        )
        points = [(x(i), y(_num(row.get(line_key)))) for i, row in enumerate(rows) if _finite(row.get(line_key))]
        return (
            ribbon_shape
            + bars
            + (
                f'<polyline points="{_points(points)}" fill="none" stroke="{line_colour}" stroke-width="2" stroke-dasharray="5 4"/>'
                if points
                else ""
            )
        )

    return _chart_frame(
        values,
        draw,
        label,
        len(rows),
        x_labels=x_labels,
        force_zero=True,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        font_size=font_size,
        max_ticks=max_ticks,
        x_label=x_label,
        stretch=True,
    )


def _merge_days(current, historical):
    history = {int(row["day"]): row for row in historical}
    return [{**row, **history.get(int(row["date"][-2:]), {})} for row in current]


def _calendar_temperature_days(rows, year, month):
    values = {int(row["date"][-2:]): row for row in rows}
    return [
        values.get(day, {"date": f"{year:04d}-{month:02d}-{day:02d}", "minimum": None, "mean": None, "maximum": None})
        for day in range(1, monthrange(year, month)[1] + 1)
    ]


def _calendar_rain_days(rows, year, month):
    values = {int(row["date"][-2:]): row for row in rows}
    return [
        values.get(day, {"date": f"{year:04d}-{month:02d}-{day:02d}", "rain": None})
        for day in range(1, monthrange(year, month)[1] + 1)
    ]


def _merge_rain_days(current, historical):
    history = {int(row["day"]): row for row in historical}
    return [{**row, **history.get(int(row["date"][-2:]), {})} for row in current]


def _merge_months(current, historical):
    actual = {row["month"]: row["cumulative"] for row in current}
    historic = {row["month"]: row for row in historical}
    return [
        {
            "current": actual.get(month),
            "historical": historic.get(month, {}).get("mean"),
            "p10": historic.get(month, {}).get("p10"),
            "p90": historic.get(month, {}).get("p90"),
        }
        for month in range(1, 13)
    ]


def _hourly_labels(rows):
    return [str(row.get("time", ""))[:2] if str(row.get("time", "")).endswith(":00") else "" for row in rows]


def _temp_kpi(value, label, footer, icon, klass):
    return f'<div class="kpi-card {klass}"><div class="kpi-icon">{_icon(icon, 34)}</div><div class="kpi-content"><div class="kpi-value">{value}</div><div class="kpi-label">{label}</div><div class="kpi-footer">{footer}</div></div></div>'


def _rain_kpi(icon, title, value, footer, colour):
    return f'<div class="rain-kpi rain-kpi-{colour}"><div class="rain-kpi-icon">{_icon(icon, 35)}</div><div class="rain-kpi-copy"><div class="rain-kpi-title">{title}</div><div class="rain-kpi-value">{value}</div><div class="rain-kpi-footer">{footer}</div></div></div>'


def _section(icon, title, subtitle, accent, right=""):
    subtitle_html = f'<div class="section-subtitle">{subtitle}</div>' if subtitle else ""
    return f'<div class="section-header"><div class="section-title-group"><div class="section-icon section-icon-{accent}">{_icon(icon, 21)}</div><div><div class="section-title">{title}</div>{subtitle_html}</div></div>{f'<div class="section-header-right">{right}</div>' if right else ""}</div>'


def _legend():
    return '<div class="legend-inline"><span class="legend-item"><i class="legend-line legend-red"></i>Máxima</span><span class="legend-item"><i class="legend-line legend-dashed"></i>Media</span><span class="legend-item"><i class="legend-line legend-blue"></i>Mínima</span></div>'


def _monthly_legend():
    return '<div class="legend-inline"><span class="legend-item"><i class="legend-line legend-red"></i>Máxima mensual</span><span class="legend-item"><i class="legend-line legend-blue"></i>Mínima mensual</span></div>'


def _monthly_extremes_analysis(summary, month):
    maximum_difference = summary.get("monthlyMaximumDifference")
    minimum_difference = summary.get("monthlyMinimumDifference")
    if maximum_difference is None or minimum_difference is None:
        return "No hay otros meses válidos para comparar los extremos térmicos."

    def describe_days(value):
        if value < -0.5:
            return "más frescos"
        if value > 0.5:
            return "más cálidos"
        return "similares"

    def describe_nights(value):
        if value < -0.5:
            return "más frescas"
        if value > 0.5:
            return "más cálidas"
        return "similares"

    return (
        f"{MONTHS[month - 1]} presentó días {describe_days(maximum_difference)} y noches "
        f"{describe_nights(minimum_difference)} respecto a los meses anteriores del año."
    )


def _historical_range_analysis(summary, month):
    comparable = int(summary.get("historicalComparableDays") or 0)
    if not comparable:
        return "No existen suficientes días con referencia histórica para realizar la comparación."
    hot = int(summary.get("historicalHotDays") or 0)
    cold = int(summary.get("historicalColdDays") or 0)
    hot_text = f"{hot} día fue" if hot == 1 else f"{hot} días fueron"
    cold_text = f"{cold} día fue" if cold == 1 else f"{cold} días fueron"
    return (
        f"Durante el mes de {MONTHS[month - 1].lower()}, {hot_text} más cálido{'s' if hot != 1 else ''} "
        f"de lo habitual y {cold_text} más frío{'s' if cold != 1 else ''} de lo habitual."
    )


def _hottest_temperature_analysis(summary, month):
    date_value = str(summary.get("hottestDate") or "")
    try:
        day = str(int(date_value[-2:]))
    except ValueError:
        day = "—"
    time_value = str(summary.get("hottestTime") or "—")
    temperature = _fmt(summary.get("hottestMaximum"), " °C")
    return (
        f"El {day} de {MONTHS[month - 1].lower()} a las {time_value} se registró "
        f"la temperatura más cálida del mes: {temperature}."
    )


def _rain_history_analysis(summary, month, year):
    total = _fmt(summary.get("total"), " mm")
    historical = _fmt(summary.get("historicalMean"), " mm")
    difference = summary.get("differencePercent")
    period = summary.get("historicalPeriod") or "disponible"
    if difference is None:
        return f"{MONTHS[month - 1]} {year} acumuló {total}; no existe un promedio histórico comparable."
    if abs(difference) < 0.5:
        return f"{MONTHS[month - 1]} {year} estuvo prácticamente en el promedio histórico {period} ({historical})."
    position = "por encima" if difference > 0 else "por debajo"
    return (
        f"{MONTHS[month - 1]} {year} acumuló {total}, {abs(difference):.0f}% {position} "
        f"del promedio histórico {period} ({historical})."
    )


def _rain_days_below_average(rows):
    comparable = [row for row in rows if _finite(row.get("rain")) and _finite(row.get("mean"))]
    if not comparable:
        return "No existen suficientes días con referencia histórica para realizar la comparación."
    below = sum(_num(row["rain"]) < _num(row["mean"]) for row in comparable)
    result = "1 registró" if below == 1 else f"{below} registraron"
    return (
        f"De los {len(comparable)} días analizados, {result} precipitaciones inferiores al promedio histórico diario."
    )


def _annual_rain_analysis(rows):
    groups = {"Sobre lo habitual": [], "Bajo lo habitual": [], "En el promedio": []}
    for month, row in enumerate(rows, start=1):
        if not (_finite(row.get("current")) and _finite(row.get("historical"))):
            continue
        difference = _num(row["current"]) - _num(row["historical"])
        label = (
            "Sobre lo habitual" if difference > 0.5 else "Bajo lo habitual" if difference < -0.5 else "En el promedio"
        )
        groups[label].append(month)
    parts = [f"{label}: {_month_ranges(months)}" for label, months in groups.items() if months]
    return " · ".join(parts) if parts else "No existe una referencia histórica comparable para los meses analizados."


def _month_ranges(months):
    ranges = []
    start = previous = months[0]
    for current in months[1:]:
        if current == previous + 1:
            previous = current
            continue
        ranges.append((start, previous))
        start = previous = current
    ranges.append((start, previous))
    labels = [
        MONTHS[start - 1].lower() if start == end else f"{MONTHS[start - 1].lower()} a {MONTHS[end - 1].lower()}"
        for start, end in ranges
    ]
    return ", ".join(labels)


def _icon(kind, size):
    paths = {
        "thermometer": '<path d="M14 14.76V5a4 4 0 0 0-8 0v9.76a6 6 0 1 0 8 0Z"/><path d="M10 9v7"/><circle cx="10" cy="18" r="2"/>',
        "trophy": '<path d="M8 21h8M12 17v4M7 4h10v4a5 5 0 0 1-10 0V4ZM7 6H4v1a4 4 0 0 0 4 4M17 6h3v1a4 4 0 0 1-4 4"/>',
        "calendar": '<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4m8-4v4M4 10h16"/>',
        "trend": '<path d="M4 18 10 12l4 4 6-9M15 7h5v5"/>',
        "chart": '<path d="M4 19V9M10 19V5M16 19v-7M22 19H2"/>',
        "flame": '<path d="M12 22c4 0 7-3 7-7 0-3-1.5-5.2-4-7.5.1 2.2-1 3.5-2.1 4.3.2-4.3-2.4-7-5.2-9.8.2 4-2.7 6.6-2.7 11 0 5 3 9 7 9Z"/>',
        "rain": '<path d="M7 16a5 5 0 0 1 1-9.9A7 7 0 0 1 21 9a4 4 0 0 1-1 7H7Zm1 3-1 2m6-2-1 2m6-2-1 2"/>',
        "drop": '<path d="M12 2S5 10 5 16a7 7 0 0 0 14 0C19 10 12 2 12 2Z"/>',
        "umbrella": '<path d="M3 12a9 9 0 0 1 18 0c-3-2-6-2-9 0-3-2-6-2-9 0Zm9 0v7a2 2 0 0 0 4 0"/>',
    }
    return f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">{paths.get(kind, paths["chart"])}</svg>'


def _write_svg(path, content):
    path.write_text(content, encoding="utf-8")


def _points(points):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _finite(value):
    return math.isfinite(_num(value))


def _fmt(value, suffix):
    return "—" if not _finite(value) else f"{_num(value):.1f}{suffix}"


def _date(value):
    parts = str(value or "").split("-")
    return "/".join(reversed(parts)) if len(parts) == 3 else "—"


def _e(value):
    return html.escape(str(value or ""), quote=True)

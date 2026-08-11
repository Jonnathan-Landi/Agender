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


def render_temperature(
    report: dict[str, Any],
    output: Path,
    year: int,
    month: int,
    rain_report: dict[str, Any] | None = None,
) -> Path:
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
        plots / "02_comparacion_mensual.svg",
        _line_svg(
            report["monthly"],
            (("maximum", "#EF2A26"), ("minimum", "#0867C8")),
            "Temperatura mensual (°C)",
            x_labels=[MONTHS_SHORT[row["month"] - 1] for row in report["monthly"]],
            points=True,
            canvas_width=900,
            canvas_height=400,
            font_size=26,
            max_ticks=12,
            x_label="Mes",
            exact_range=True,
            range_padding=0.5,
            show_values=True,
            left_margin=112,
            x_tick_font_size=26,
            x_title_font_size=29,
            x_label_angle=-45,
            x_edge_padding=24,
            line_width=4.0,
            point_radius=4.5,
            value_label_font_size=23,
            stretch=True,
            y_title_font_size=24,
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
            "Temperatura diaria (°C)",
            x_labels=daily_labels,
            ribbons=(("minimumP10", "minimumP90", "#CFE0F2"), ("maximumP10", "maximumP90", "#F8CACA")),
            canvas_width=900,
            canvas_height=400,
            font_size=26,
            max_ticks=20,
            x_label="Día del mes",
            x_minor_ticks=True,
            x_tick_font_size=26,
            x_title_font_size=29,
            y_title_font_size=28,
            stretch=True,
        ),
    )
    if rain_report is not None:
        rain_summary = rain_report["summary"]
        monthly_rain = [row for row in rain_report["monthly"] if row["month"] <= month]
        _write_svg(
            plots / "05_lluvia_mensual.svg",
            _bar_svg(
                monthly_rain,
                "value",
                "#1970CE",
                "Precipitación mensual (mm)",
                x_labels=[MONTHS_SHORT[row["month"] - 1] for row in monthly_rain],
                canvas_width=900,
                canvas_height=400,
                font_size=26,
                x_label="Mes",
                x_tick_font_size=26,
                x_title_font_size=29,
                y_title_font_size=28,
                bar_stroke="#111827",
                bar_stroke_width=2.2,
                bar_width_ratio=0.72,
            ),
        )
        rain_history = [*rain_report["history"], {"year": year, "value": rain_summary["total"]}]
        _write_svg(
            plots / "06_historia_lluvia.svg",
            _bar_svg(
                rain_history,
                "value",
                "#87C7DF",
                "Precipitación mensual (mm)",
                highlight=len(rain_history) - 1,
                reference=rain_summary["historicalMean"],
                canvas_width=900,
                canvas_height=400,
                font_size=26,
                x_label="Año",
                max_ticks=len(rain_history),
                x_tick_font_size=25,
                x_title_font_size=29,
                y_title_font_size=25,
                x_label_angle=-45,
                y_title_offset=16,
                x_tick_bottom_offset=82,
            ),
        )
    comparison = _monthly_extremes_analysis(summary, month)
    historical_analysis = _historical_range_analysis(summary, month)
    rain_monthly_card = ""
    rain_history_card = ""
    rain_summary_card = ""
    if rain_report is not None:
        rain_summary = rain_report["summary"]
        rain_history_analysis = _rain_history_rank_analysis(rain_summary, rain_report["history"], month, year)
        rain_monthly_analysis = _monthly_rain_rank_analysis(rain_report["monthly"], month, year)
        rain_summary_card = _combined_summary_card(
            f"Resumen de precipitaciones · {period}",
            "rain",
            "summary-rain",
            (
                (_fmt(rain_summary["total"], " mm"), f"ACUMULADO DE {MONTHS[month - 1].upper()}"),
                (f'{rain_summary["rainDays"]} días', "DÍAS CON LLUVIA"),
                (_fmt(rain_summary["maximum"], " mm"), "MÁXIMA DIARIA"),
            ),
        )
        rain_monthly_card = f'''<section class="report-card card-daily">{_section("chart", f"Lluvia mensual durante {year}", rain_monthly_analysis, "blue")}<div class="plot-wrap plot-daily"><img class="plot-svg" src="plots/05_lluvia_mensual.svg"></div></section>'''
        rain_history_card = f'''<section class="report-card card-hot">{_section("chart", f"¿Cómo fue {MONTHS[month - 1].lower()} frente a otros años?", rain_history_analysis, "blue")}<div class="plot-wrap plot-hot"><img class="plot-svg" src="plots/06_historia_lluvia.svg"></div></section>'''
    document = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="assets/report.css"><title>Seguimiento térmico</title></head><body>
<main class="dashboard-shell">
  <section class="summary-grid">
    {_combined_summary_card(f"Resumen térmico · {period}", "thermometer", "summary-temperature", ((_fmt(summary["minimum"], " °C"), "MÍNIMA ABSOLUTA"), (_fmt(summary["mean"], " °C"), "TEMPERATURA MEDIA"), (_fmt(summary["maximum"], " °C"), "MÁXIMA ABSOLUTA")))}
    {rain_summary_card}
  </section>
  {rain_monthly_card}
  <section class="middle-grid"><article class="report-card card-monthly">{_section("thermometer", f"Temperaturas mensuales durante {year}", comparison, "blue", _monthly_legend())}<div class="monthly-plot-zone"><img class="plot-svg" src="plots/02_comparacion_mensual.svg"></div></article>
  <article class="report-card card-history">{_section("chart", f"¿{MONTHS[month - 1]} estuvo dentro de lo habitual?", historical_analysis, "red")}{_historical_legend(month, year)}<div class="plot-wrap plot-history"><img class="plot-svg" src="plots/03_comparacion_historica.svg"></div></article></section>
  {rain_history_card}
</main></body></html>"""
    report_file = target / "reporte_temperatura.html"
    report_file.write_text(document, encoding="utf-8")
    return report_file


def render_flows(cards: list[dict[str, Any]], output: Path, year: int, month: int) -> Path:
    target = output / f"caudales_{year:04d}_{month:02d}"
    plots = target / "plots"
    plots.mkdir(parents=True, exist_ok=True)
    card_html = []
    for card in cards:
        error = card.get("error")
        if error:
            content = f'<div class="flow-error">{_e(error)}</div>'
        else:
            filename = f'{card["id"]}.svg'
            _write_svg(plots / filename, _rain_flow_svg(card["data"]))
            content = f'<img src="plots/{filename}" alt="Lluvia y caudal de {_e(card["label"])}">'
        subtitle = _rain_flow_analysis(card.get("data", []), month) if not error else "No fue posible analizar este periodo."
        card_html.append(
            f'<article class="flow-card"><header><h2>Lluvia vs Caudal mensual en {_e(card["label"])}</h2>'
        f'<p>{_e(subtitle)}</p>'
            f'</header><div class="flow-chart">{content}</div></article>'
        )
    document = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
*{{box-sizing:border-box}}html,body{{height:100%;margin:0;background:#f5f8fc;color:#14233a;font-family:"Segoe UI",Arial,sans-serif;overflow:hidden}}body{{padding:10px}}
.flow-grid{{height:100%;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:repeat(2,minmax(0,1fr));gap:10px}}
.flow-card{{min-width:0;min-height:0;overflow:hidden;background:#fff;border:1px solid #dfe6ee;border-radius:15px;box-shadow:0 2px 10px rgba(15,32,55,.06)}}
.flow-card header{{height:82px;padding:10px 16px;background:linear-gradient(90deg,#eef7ff,#fff);border-bottom:1px solid #dfe6ee}}
.flow-card h2{{margin:0;color:#073f87;font-size:22px}}.flow-card p{{margin:5px 0 0;color:#365078;font-size:18px;line-height:1.3}}
.flow-chart{{height:calc(100% - 82px);display:grid;place-items:center;padding:2px 8px 6px}}.flow-chart img{{width:100%;height:100%;object-fit:fill}}
.flow-error{{max-width:430px;padding:18px;text-align:center;color:#9f2d20;background:#fff0ee;border-radius:10px;font-weight:650}}
</style><title>Seguimiento de Caudales</title></head><body><main class="flow-grid">{"".join(card_html)}</main></body></html>'''
    report_file = target / "reporte_caudales.html"
    report_file.write_text(document, encoding="utf-8")
    return report_file


def _rain_flow_analysis(rows: list[dict[str, Any]], month: int) -> str:
    """Rank the selected month's flow among valid months since January 2026."""
    month_name = MONTHS[month - 1].lower()
    if not rows or not _finite(rows[-1].get("flow")):
        return f"El caudal de {month_name} no cuenta con datos suficientes para establecer su posición."

    current = _num(rows[-1]["flow"])
    values = [_num(row["flow"]) for row in rows if _finite(row.get("flow"))]
    high_rank = 1 + sum(value > current for value in values)
    low_rank = 1 + sum(value < current for value in values)
    use_high_rank = high_rank < low_rank
    rank = high_rank if use_high_rank else low_rank
    direction = "alto" if use_high_rank else "bajo"
    if rank == 1:
        position = f"el más {direction}"
    else:
        ordinals = {
            2: "segundo",
            3: "tercer",
            4: "cuarto",
            5: "quinto",
            6: "sexto",
            7: "séptimo",
            8: "octavo",
            9: "noveno",
            10: "décimo",
            11: "undécimo",
            12: "duodécimo",
        }
        ordinal = ordinals.get(rank, f"N.º {rank}")
        position = f"el {ordinal} caudal más {direction}"
    return f"El caudal de {month_name} fue {position} desde enero de 2026."


def _rain_flow_svg(rows: list[dict[str, Any]]) -> str:
    width, height = 820, 330
    left, right = 94, 94
    rain_top, rain_bottom = 22, 130
    flow_top, flow_bottom = 136, 270
    rains = [_num(row.get("rain")) for row in rows if _finite(row.get("rain"))]
    flows = [_num(row.get("flow")) for row in rows if _finite(row.get("flow"))]
    rain_max = max(rains, default=1.0) or 1.0
    flow_max = max(flows, default=1.0) or 1.0
    count = max(1, len(rows))
    plot_width = width - left - right

    def x(index):
        return left + (index + 0.5) / count * plot_width

    def rain_y(value):
        return rain_top + value / rain_max * (rain_bottom - rain_top)

    def flow_y(value):
        return flow_bottom - value / flow_max * (flow_bottom - flow_top)

    bar_width = max(3.0, plot_width / count * 0.62)
    bars = "".join(
        f'<rect x="{x(index) - bar_width / 2:.1f}" y="{rain_top}" width="{bar_width:.1f}" height="{rain_y(_num(row.get("rain"))) - rain_top:.1f}" rx="2" fill="#2f9de0" opacity=".82"/>'
        for index, row in enumerate(rows)
        if _finite(row.get("rain"))
    )
    segments: list[list[tuple[float, float]]] = []
    for index, row in enumerate(rows):
        if _finite(row.get("flow")):
            if not segments or (index > 0 and not _finite(rows[index - 1].get("flow"))):
                segments.append([])
            segments[-1].append((x(index), flow_y(_num(row.get("flow")))))
    points = [point for segment in segments for point in segment]
    line = "".join(
        f'<polyline points="{_points(segment)}" fill="none" stroke="#ed6b21" stroke-width="3.5" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
        for segment in segments
    )
    dots = "".join(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" fill="#ed6b21"/>' for px, py in points)
    rain_grid = "".join(
        f'<line x1="{left}" y1="{rain_top + index * (rain_bottom-rain_top)/2:.1f}" x2="{width-right}" y2="{rain_top + index * (rain_bottom-rain_top)/2:.1f}" stroke="#dfe7ef"/>'
        for index in range(2)
    )
    flow_grid = "".join(
        f'<line x1="{left}" y1="{flow_top + index * (flow_bottom-flow_top)/2:.1f}" x2="{width-right}" y2="{flow_top + index * (flow_bottom-flow_top)/2:.1f}" stroke="#dfe7ef"/>'
        for index in range(1, 3)
    )
    left_ticks = "".join(
        f'<text x="{left-9}" y="{rain_top + index*(rain_bottom-rain_top)/2 + 4:.1f}" text-anchor="end">{rain_max*index/2:.1f}</text>'
        for index in range(3)
    )
    right_ticks = "".join(
        f'<text x="{width-right+9}" y="{flow_bottom - index*(flow_bottom-flow_top)/2 + 4:.1f}" text-anchor="start">{flow_max*index/2:.1f}</text>'
        for index in range(3)
    )
    labels = "".join(
        f'<text class="month-label" x="{x(index):.1f}" y="296" text-anchor="middle">{MONTHS_SHORT[int(row["period"][-2:])-1]}</text>'
        for index, row in enumerate(rows)
        if index % max(1, math.ceil(count / 12)) == 0
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" preserveAspectRatio="none"><defs><linearGradient id="monthly-bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#edf8ff"/><stop offset="48%" stop-color="#f8fbfd"/><stop offset="52%" stop-color="#fdfaf7"/><stop offset="100%" stop-color="#fff5ec"/></linearGradient></defs><style>text{{font:18px Segoe UI,Arial;fill:#475569;font-weight:650}}.title{{font-size:20px;font-weight:800}}.month-label{{font-size:18px;font-weight:750}}.x-title{{font-size:20px;font-weight:800}}</style><rect x="{left}" y="{rain_top}" width="{plot_width}" height="{flow_bottom-rain_top}" rx="7" fill="url(#monthly-bg)"/>{rain_grid}{flow_grid}{bars}{line}{dots}{left_ticks}{right_ticks}{labels}<text class="title" x="25" y="{(rain_top+rain_bottom)/2}" text-anchor="middle" transform="rotate(-90 25 {(rain_top+rain_bottom)/2})">Lluvia (mm)</text><text class="title" x="{width-23}" y="{(flow_top+flow_bottom)/2}" text-anchor="middle" transform="rotate(90 {width-23} {(flow_top+flow_bottom)/2})">Caudal (m³/s)</text><text class="x-title" x="{width/2}" y="324" text-anchor="middle">Mes</text></svg>'''


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
    x_tick_font_size: int | None = None,
    x_title_font_size: int | None = None,
    x_label_angle: int = 0,
    x_edge_padding: int = 0,
    value_label_font_size: int = 17,
    y_title_font_size: int | None = None,
    x_minor_ticks: bool = False,
    y_title_offset: int = 0,
    x_tick_bottom_offset: int | None = None,
) -> str:
    width, height = canvas_width, canvas_height
    left = left_margin or (112 if font_size >= 21 else (100 if font_size >= 18 else (88 if font_size >= 16 else 68)))
    bottom_offset = 108 if x_label_angle else (76 if x_label else 60)
    right, top, bottom = 24, 28, height - bottom_offset
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
        usable_left = left + x_edge_padding
        usable_right = width - right - x_edge_padding
        return usable_left + (index / max(1, count - 1)) * (usable_right - usable_left)

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
    angled_tick_offset = x_tick_bottom_offset if x_tick_bottom_offset is not None else 70
    tick_y = height - (angled_tick_offset if x_label_angle else (42 if x_label else 25))
    tick_style = f' style="font-size:{x_tick_font_size}px"' if x_tick_font_size else ""
    ticks = "".join(
        f'<text class="axis-tick" x="{x(index):.1f}" y="{tick_y}" text-anchor="{("end" if x_label_angle else "middle")}"{tick_style}'
        f'{f" transform=\"rotate({x_label_angle} {x(index):.1f} {tick_y})\"" if x_label_angle else ""}>{_e(value)}</text>'
        for index, value in tick_labels
    )
    minor_ticks = (
        "".join(
            f'<line x1="{x(index):.1f}" y1="{bottom:.1f}" x2="{x(index):.1f}" y2="{bottom + 11:.1f}" '
            'stroke="#94A3B8" stroke-width="1.4"/>'
            for index in range(count)
        )
        if x_minor_ticks
        else ""
    )
    axis_center = (top + bottom) / 2 + y_title_offset
    x_title = (
        f'<text class="axis-title" x="{(left + width - right) / 2:.1f}" y="{height - (12 if x_label_angle else 6)}" text-anchor="middle"'
        f'{f" style=\"font-size:{x_title_font_size}px\"" if x_title_font_size else ""}>{_e(x_label)}</text>'
        if x_label
        else ""
    )
    aspect = ' preserveAspectRatio="none"' if stretch else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"{aspect}><style>text{{font:{font_size}px Segoe UI,Arial;fill:#334155}}.axis-tick{{font-weight:650}}.axis-title{{font-size:{font_size + 2}px;font-weight:750}}.axis-title-y{{font-size:{y_title_font_size or font_size + 2}px}}.value-label{{font-size:{value_label_font_size}px;font-weight:750;paint-order:stroke;stroke:#fff;stroke-width:4px;stroke-linejoin:round}}.peak-label{{font-size:{font_size + 5}px;font-weight:800;paint-order:stroke;stroke:#fff;stroke-width:6px;stroke-linejoin:round}}line{{shape-rendering:crispEdges}}</style>{grid}{minor_ticks}<text class="axis-title axis-title-y" x="{-axis_center:.1f}" y="24" text-anchor="middle" transform="rotate(-90)">{_e(label)}</text>{draw(x, y, bottom)}{ticks}{x_title}</svg>'


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
    x_tick_font_size=None,
    x_title_font_size=None,
    x_label_angle=0,
    x_edge_padding=0,
    line_width=2.5,
    point_radius=3.5,
    value_label_font_size=17,
    y_title_font_size=None,
    x_minor_ticks=False,
    y_title_offset=0,
    x_tick_bottom_offset=None,
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
                    f'<polyline points="{_points(pts)}" fill="none" stroke="{colour}" stroke-width="{line_width}" stroke-dasharray="{dash[0] if dash else "none"}" stroke-linejoin="round"/>'
                )
            if points:
                parts.extend(
                    f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{point_radius}" fill="{colour}"/>'
                    for px, py in pts
                )
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
        x_tick_font_size=x_tick_font_size,
        x_title_font_size=x_title_font_size,
        x_label_angle=x_label_angle,
        x_edge_padding=x_edge_padding,
        value_label_font_size=value_label_font_size,
        y_title_font_size=y_title_font_size,
        x_minor_ticks=x_minor_ticks,
        y_title_offset=y_title_offset,
        x_tick_bottom_offset=x_tick_bottom_offset,
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
    x_tick_font_size=None,
    x_title_font_size=None,
    y_title_font_size=None,
    bar_stroke="none",
    bar_stroke_width=0,
    bar_width_ratio=0.62,
    max_ticks=None,
    x_label_angle=0,
    y_title_offset=0,
    x_tick_bottom_offset=None,
):
    values = [_num(row.get(key)) for row in rows]

    def draw(x, y, bottom):
        bar_width = max(8, (canvas_width - 130) / max(1, len(rows)) * bar_width_ratio)
        bars = "".join(
            f'<rect x="{x(i) - bar_width / 2:.1f}" y="{y(value):.1f}" width="{bar_width:.1f}" height="{max(1, bottom - y(value)):.1f}" fill="{("#146FC4" if highlight == i else colour)}" stroke="{bar_stroke}" stroke-width="{bar_stroke_width}"/>'
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
        max_ticks=max_ticks,
        x_label=x_label,
        categorical_x=True,
        stretch=True,
        x_tick_font_size=x_tick_font_size,
        x_title_font_size=x_title_font_size,
        y_title_font_size=y_title_font_size,
        x_label_angle=x_label_angle,
        y_title_offset=y_title_offset,
        x_tick_bottom_offset=x_tick_bottom_offset,
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












def _combined_summary_card(title, icon, klass, metrics):
    items = "".join(
        f'<div class="summary-metric"><strong>{value}</strong><span>{label}</span></div>'
        for value, label in metrics
    )
    return (
        f'<article class="combined-summary {klass}">'
        f'<div class="summary-heading"><span class="summary-icon">{_icon(icon, 28)}</span><h2>{title}</h2></div>'
        f'<div class="summary-metrics">{items}</div></article>'
    )




def _section(icon, title, subtitle, accent, right=""):
    subtitle_html = f'<div class="section-subtitle">{subtitle}</div>' if subtitle else ""
    return f'<div class="section-header"><div class="section-title-group"><div class="section-icon section-icon-{accent}">{_icon(icon, 21)}</div><div><div class="section-title">{title}</div>{subtitle_html}</div></div>{f'<div class="section-header-right">{right}</div>' if right else ""}</div>'




def _monthly_legend():
    return '<div class="legend-inline"><span class="legend-item"><i class="legend-line legend-red"></i>Máxima mensual</span><span class="legend-item"><i class="legend-line legend-blue"></i>Mínima mensual</span></div>'


def _historical_legend(month, year):
    period = f"{MONTHS[month - 1]} {year}"
    return f'''<div class="historical-legend" aria-label="Leyenda de comparación histórica">
      <span><i class="history-mark history-red-solid"></i>Máxima · {period}</span>
      <span><i class="history-mark history-red-dashed"></i>Máxima · promedio histórico</span>
      <span><i class="history-mark history-red-band"></i>Máxima · rango P10-P90</span>
      <span><i class="history-mark history-blue-solid"></i>Mínima · {period}</span>
      <span><i class="history-mark history-blue-dashed"></i>Mínima · promedio histórico</span>
      <span><i class="history-mark history-blue-band"></i>Mínima · rango P10-P90</span>
    </div>'''


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
    if comparable:
        hot = int(summary.get("historicalHotDays") or 0)
        cold = int(summary.get("historicalColdDays") or 0)
        hot_text = f"{hot} día fue más caliente" if hot == 1 else f"{hot} días fueron más calientes"
        cold_text = f"{cold} día más frío" if cold == 1 else f"{cold} días más fríos"
        comparison = (
            f"Durante {MONTHS[month - 1].lower()}, {hot_text} de lo habitual y {cold_text}."
        )
    else:
        comparison = "No existen suficientes días con referencia histórica para realizar la comparación."

    date_value = str(summary.get("hottestDate") or "")
    try:
        day = str(int(date_value[-2:]))
    except ValueError:
        day = ""
    if not _finite(summary.get("hottestMaximum")):
        return comparison
    temperature = _fmt(summary.get("hottestMaximum"), " °C")
    date_text = f", registrada el {day} de {MONTHS[month - 1].lower()}" if day else ""
    return f"{comparison} La temperatura máxima del mes fue de {temperature}{date_text}."


def _rain_history_rank_analysis(summary, history, month, year):
    total = _fmt(summary.get("total"), " mm")
    historical = _fmt(summary.get("historicalMean"), " mm")
    difference = summary.get("differencePercent")
    if difference is None:
        return f"{MONTHS[month - 1]} {year} acumuló {total}; no existe un promedio histórico comparable."

    magnitude = abs(_num(difference))
    if magnitude < 0.5:
        comparison = f"prácticamente igual al promedio histórico de {historical}"
    else:
        direction = "por encima" if difference > 0 else "por debajo"
        qualifier = "ligeramente " if magnitude <= 10 else "muy " if magnitude > 25 else ""
        comparison = f"{qualifier}{direction} del promedio histórico de {historical}"

    comparable = [
        (int(row["year"]), _num(row.get("value")))
        for row in history
        if _finite(row.get("value")) and int(row.get("year") or 0) != year
    ]
    if not _finite(summary.get("total")):
        return f"{MONTHS[month - 1]} {year} no cuenta con un acumulado válido para la comparación histórica."
    current = _num(summary["total"])
    all_values = [value for _row_year, value in comparable] + [current]
    first_year = min([row_year for row_year, _value in comparable] + [year])
    wet_rank = 1 + sum(value > current + 0.05 for value in all_values)
    dry_rank = 1 + sum(value < current - 0.05 for value in all_values)
    use_wet_rank = wet_rank <= dry_rank
    rank = wet_rank if use_wet_rank else dry_rank
    condition = "lluvioso" if use_wet_rank else "seco"
    rank_text = _rain_rank_text(rank, month, condition)
    return (
        f"{MONTHS[month - 1]} {year} acumuló {total}, {comparison}, "
        f"ubicándose como {rank_text} desde {first_year}."
    )


def _rain_rank_text(rank, month, condition):
    month_name = MONTHS[month - 1].lower()
    if rank == 1:
        return f"el {month_name} más {condition}"
    ordinals = {
        2: "segundo",
        3: "tercer",
        4: "cuarto",
        5: "quinto",
        6: "sexto",
        7: "séptimo",
        8: "octavo",
        9: "noveno",
        10: "décimo",
    }
    if rank in ordinals:
        return f"el {ordinals[rank]} {month_name} más {condition}"
    return f"el {month_name} N.º {rank} entre los más {condition}s"




def _monthly_rain_rank_analysis(rows, month, year):
    comparable = [
        (int(row["month"]), _num(row.get("value")))
        for row in rows
        if int(row.get("month") or 0) <= month and _finite(row.get("value"))
    ]
    current = next((value for row_month, value in comparable if row_month == month), None)
    month_name = MONTHS[month - 1]
    if current is None:
        return f"{month_name} no cuenta con un acumulado válido para compararlo con los demás meses de {year}."
    if len(comparable) == 1:
        return f"{month_name} fue el único mes de {year} con datos válidos de precipitación."

    tolerance = 0.05
    wetter = sum(value > current + tolerance for _row_month, value in comparable)
    drier = sum(value < current - tolerance for _row_month, value in comparable)
    tied = sum(abs(value - current) <= tolerance for _row_month, value in comparable)
    wet_rank = wetter + 1
    dry_rank = drier + 1

    if tied > 1 and wet_rank == 1:
        return f"{month_name} estuvo empatado como el mes más lluvioso de {year}."
    if tied > 1 and dry_rank == 1:
        return f"{month_name} estuvo empatado como el mes más seco de {year}."
    if wet_rank == 1:
        return f"{month_name} fue el mes más lluvioso de {year}."
    if dry_rank == 1:
        return f"{month_name} fue el mes más seco de {year}."
    if wet_rank == 2:
        return f"{month_name} fue el segundo mes más lluvioso de {year}."
    if dry_rank == 2:
        return f"{month_name} fue el segundo mes más seco de {year}."

    if wet_rank <= dry_rank:
        return f"{month_name} ocupó el puesto N.º {wet_rank} entre los meses más lluviosos de {year}."
    return f"{month_name} ocupó el puesto N.º {dry_rank} entre los meses más secos de {year}."






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




def _e(value):
    return html.escape(str(value or ""), quote=True)

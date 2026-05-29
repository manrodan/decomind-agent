"""
Gráficos para el dossier PDF — reportlab.graphics nativo (sin matplotlib).

Cada función devuelve un Drawing (flowable de Platypus) listo para append a
la story. Estilo coherente con el branding (color primario configurable).
"""

from __future__ import annotations

from typing import Any

from reportlab.graphics.charts.barcharts import (
    HorizontalBarChart,
    VerticalBarChart,
)
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.units import mm


def _hex(h: str) -> colors.Color:
    try:
        return colors.HexColor(h)
    except Exception:
        return colors.HexColor("#1F6FEB")


def _eur_label(v: float) -> str:
    if v >= 1000:
        return f"{v/1000:.0f}k€"
    return f"{v:.0f}€"


def budget_by_room_chart(by_room: list[dict[str, Any]], primary_hex: str,
                         kind_labels: dict[str, str] | None = None) -> Drawing:
    """Barras horizontales: coste de reforma por estancia."""
    kind_labels = kind_labels or {}
    rooms = [(kind_labels.get(str(r.get("kind", "")), str(r.get("kind", ""))),
              float(r.get("total_integral", 0))) for r in by_room]
    rooms = [r for r in rooms if r[1] > 0]

    width, height = 471, max(90, 22 * len(rooms) + 40)
    d = Drawing(width, height)

    chart = HorizontalBarChart()
    chart.x = 95
    chart.y = 15
    chart.width = width - 150
    chart.height = height - 30
    chart.data = [[r[1] for r in rooms]]
    chart.bars[0].fillColor = _hex(primary_hex)
    chart.bars[0].strokeColor = None
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labelTextFormat = lambda v: _eur_label(v)
    chart.valueAxis.labels.fontSize = 7
    chart.categoryAxis.categoryNames = [r[0] for r in rooms]
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.boxAnchor = "e"
    chart.categoryAxis.labels.dx = -4
    chart.barWidth = 11
    chart.groupSpacing = 6
    d.add(chart)

    # etiqueta de valor al final de cada barra
    max_v = max((r[1] for r in rooms), default=1)
    for i, (_, v) in enumerate(rooms):
        bar_w = (chart.width) * (v / max_v) if max_v else 0
        y = chart.y + chart.height - (chart.height / len(rooms)) * (i + 0.5)
        d.add(String(chart.x + bar_w + 4, y - 3, _eur_label(v),
                     fontSize=7, fillColor=_hex("#374151")))
    return d


def roi_chart(current: float, investment: float, post: float, net: float,
              primary_hex: str) -> Drawing:
    """Barras verticales: valor actual, inversión, post-reforma, ganancia neta."""
    cats = ["Current", "Renovation", "After reno.", "Net gain"]
    vals = [current, investment, post, net]
    bar_colors = [
        _hex("#9CA3AF"), _hex("#F59E0B"), _hex(primary_hex), _hex("#15803D"),
    ]

    width, height = 471, 150
    d = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x = 40
    chart.y = 25
    chart.width = width - 70
    chart.height = height - 45
    chart.data = [vals]
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labelTextFormat = lambda v: _eur_label(v)
    chart.valueAxis.labels.fontSize = 7
    chart.categoryAxis.categoryNames = cats
    chart.categoryAxis.labels.fontSize = 8
    chart.barWidth = 26
    chart.groupSpacing = 22
    # color por barra
    for i, c in enumerate(bar_colors):
        chart.bars[(0, i)].fillColor = c
        chart.bars[(0, i)].strokeColor = None
    d.add(chart)

    # etiqueta encima de cada barra
    max_v = max(vals) if max(vals) else 1
    n = len(vals)
    slot = chart.width / n
    for i, v in enumerate(vals):
        bar_h = chart.height * (v / max_v) if max_v else 0
        x = chart.x + slot * (i + 0.5)
        d.add(String(x, chart.y + bar_h + 4, _eur_label(v),
                     fontSize=8, fillColor=_hex("#111827"), textAnchor="middle"))
    return d


def price_sources_chart(notariado: float, mitma: float, primary_hex: str) -> Drawing:
    """Barras verticales pequeñas: Notariado (real) vs MITMA (tasación)."""
    cats, vals = [], []
    bar_colors = []
    if notariado:
        cats.append("Notariado\n(real)"); vals.append(notariado)
        bar_colors.append(_hex(primary_hex))
    if mitma:
        cats.append("MITMA\n(appraisal)"); vals.append(mitma)
        bar_colors.append(_hex("#9CA3AF"))

    width, height = 230, 120
    d = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x = 35
    chart.y = 20
    chart.width = width - 55
    chart.height = height - 40
    chart.data = [vals]
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labelTextFormat = lambda v: f"{v:.0f}"
    chart.valueAxis.labels.fontSize = 7
    chart.categoryAxis.categoryNames = cats
    chart.categoryAxis.labels.fontSize = 7
    chart.barWidth = 34
    chart.groupSpacing = 28
    for i, c in enumerate(bar_colors):
        chart.bars[(0, i)].fillColor = c
        chart.bars[(0, i)].strokeColor = None
    d.add(chart)

    max_v = max(vals) if vals and max(vals) else 1
    n = len(vals)
    slot = chart.width / n if n else chart.width
    for i, v in enumerate(vals):
        bar_h = chart.height * (v / max_v) if max_v else 0
        x = chart.x + slot * (i + 0.5)
        d.add(String(x, chart.y + bar_h + 3, f"{v:.0f} €/m²",
                     fontSize=7, fillColor=_hex("#111827"), textAnchor="middle"))
    return d

"""
Tarifas base de reforma por oficio (España, 2026).

Portado (copia, no rama) de decomind-partner-api/shared/labor_costs.py.
Lógica idéntica para garantizar paridad de presupuesto con producción.

Valores expresados en €. Tiers: economy (0.70) / standard (1.00) / premium (1.60).

Estos valores son estimaciones orientativas. El output debe llevar disclaimer:
no es una oferta vinculante.
"""

from __future__ import annotations

from typing import Literal

BudgetTier = Literal["economy", "standard", "premium"]

TIER_MULTIPLIER: dict[str, float] = {
    "economy": 0.70,
    "standard": 1.00,
    "premium": 1.60,
}

BASE_RATES = {
    "painting_per_sqm": 18.0,
    "masonry_per_sqm": 55.0,
    "plumbing_bathroom_fixed": 1800.0,
    "plumbing_kitchen_fixed": 1100.0,
    "electrical_base_fixed": 420.0,
    "electrical_per_point": 65.0,
    "labor_per_sqm": 90.0,
}

_DEFAULT_AREA_SQM = 12.0
_DEFAULT_ELECTRICAL_POINTS = 3

DEFAULT_AREA_SQM: dict[str, float] = {
    "salon": 22.0,
    "master_bedroom": 14.0,
    "secondary_bedroom": 12.0,
    "kids_bedroom": 10.0,
    "kitchen": 10.0,
    "bathroom": 5.0,
    "dining_room": 16.0,
    "office": 10.0,
    "hallway": 6.0,
    "terrace": 10.0,
    "laundry": 5.0,
    "storage": 4.0,
    "other": 12.0,
}

ELECTRICAL_POINTS: dict[str, int] = {
    "salon": 4,
    "master_bedroom": 3,
    "secondary_bedroom": 3,
    "kids_bedroom": 3,
    "kitchen": 6,
    "bathroom": 3,
    "dining_room": 3,
    "office": 4,
    "hallway": 2,
    "terrace": 2,
    "laundry": 3,
    "storage": 1,
    "other": 3,
}

VALID_KINDS = list(DEFAULT_AREA_SQM.keys())


def _round2(x: float) -> float:
    return round(float(x) + 1e-9, 2)


def compute_room_labor(
    kind: str,
    area_sqm: float | None,
    tier: str = "standard",
) -> dict:
    """Desglose por oficio para una estancia (lógica idéntica a producción)."""
    mult = TIER_MULTIPLIER.get(tier, 1.0)
    default_area = DEFAULT_AREA_SQM.get(kind, _DEFAULT_AREA_SQM)
    area = float(area_sqm) if area_sqm and area_sqm > 0 else default_area

    painting = BASE_RATES["painting_per_sqm"] * area * mult

    if kind in ("kitchen", "bathroom"):
        masonry = BASE_RATES["masonry_per_sqm"] * area * mult
    elif kind in ("terrace", "laundry", "storage"):
        masonry = BASE_RATES["masonry_per_sqm"] * area * 0.50 * mult
    else:
        masonry = BASE_RATES["masonry_per_sqm"] * area * 0.25 * mult

    if kind == "bathroom":
        plumbing = BASE_RATES["plumbing_bathroom_fixed"] * mult
    elif kind == "kitchen":
        plumbing = BASE_RATES["plumbing_kitchen_fixed"] * mult
    elif kind == "laundry":
        plumbing = BASE_RATES["plumbing_kitchen_fixed"] * 0.40 * mult
    else:
        plumbing = 0.0

    points = ELECTRICAL_POINTS.get(kind, _DEFAULT_ELECTRICAL_POINTS)
    electrical = (
        BASE_RATES["electrical_base_fixed"]
        + BASE_RATES["electrical_per_point"] * points
    ) * mult

    labor = BASE_RATES["labor_per_sqm"] * area * mult

    total_minima = painting + labor * 0.30
    total_integral = painting + masonry + plumbing + electrical + labor

    return {
        "kind": kind,
        "tier": tier,
        "area_sqm": _round2(area),
        "painting": _round2(painting),
        "masonry": _round2(masonry),
        "plumbing": _round2(plumbing),
        "electrical": _round2(electrical),
        "labor": _round2(labor),
        "total_minima": _round2(total_minima),
        "total_integral": _round2(total_integral),
    }

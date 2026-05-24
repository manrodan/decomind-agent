"""
MCP server: Renovation (presupuesto de reforma por estancia y vivienda).

Dos tools:
  - estimate_room_cost: presupuesto de UNA estancia con desglose por oficio.
  - estimate_renovation_plan: presupuesto completo de la vivienda (lista de
    estancias) con totales agregados, en variante mínima e integral.

Lógica portada (copia) de decomind-partner-api/shared/labor_costs.py. Paridad
de cálculo con producción para que la valoración del agente sea consistente
con los presupuestos que Decomind ya emite.

El output incluye desglose por oficio (pintura, albañilería, fontanería,
electricidad, mano de obra) — auditable, no caja negra. El agente puede
encadenar este resultado con compute_renovation_roi para cerrar el dossier.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_servers.renovation.rates import (
    TIER_MULTIPLIER,
    VALID_KINDS,
    _round2,
    compute_room_labor,
)

logger = logging.getLogger("mcp.renovation")
mcp = FastMCP("renovation")

DISCLAIMER = (
    "Estimación orientativa basada en tarifas medias de mercado España 2026. "
    "No constituye oferta vinculante; el coste real depende de calidad de "
    "acabados, accesibilidad de la obra y disponibilidad del oficio."
)


@mcp.tool()
def estimate_room_cost(
    kind: str,
    area_sqm: float = 0,
    tier: str = "standard",
) -> dict[str, Any]:
    """Estima el coste de reformar una estancia.

    Args:
        kind: Tipo de estancia. Valores reconocidos: salon, master_bedroom,
            secondary_bedroom, kids_bedroom, kitchen, bathroom, dining_room,
            office, hallway, terrace, laundry, storage, other.
            Cualquier otro string se trata como "other".
        area_sqm: Superficie de la estancia en m². 0 = usar default por tipo.
        tier: "economy" | "standard" | "premium". Default "standard".
            economy = 0.70x · standard = 1.00x · premium = 1.60x.

    Returns:
        Desglose por oficio (painting, masonry, plumbing, electrical, labor)
        + dos totales: total_minima (refresco) y total_integral (reforma completa).
    """
    if tier not in TIER_MULTIPLIER:
        tier = "standard"
    breakdown = compute_room_labor(kind=kind, area_sqm=area_sqm or None, tier=tier)
    breakdown["disclaimer"] = DISCLAIMER
    return breakdown


@mcp.tool()
def estimate_renovation_plan(
    rooms: list[dict[str, Any]],
    tier: str = "standard",
) -> dict[str, Any]:
    """Estima el coste de una reforma completa de vivienda.

    Args:
        rooms: Lista de estancias. Cada una: {kind, area_sqm?}.
            Ejemplo: [{"kind":"salon","area_sqm":24},
                      {"kind":"kitchen","area_sqm":11},
                      {"kind":"bathroom"}]
        tier: "economy" | "standard" | "premium". Default "standard".

    Returns:
        {
          "rooms_count": int,
          "tier": str,
          "by_room": [<desglose por estancia>],
          "totals": {
              painting, masonry, plumbing, electrical, labor,
              minima,       # solo refresco (pintura + 30% MO)
              integral,     # reforma completa
          },
          "rooms_aggregated_area_sqm": float,
          "disclaimer": str
        }
    """
    if tier not in TIER_MULTIPLIER:
        tier = "standard"

    by_room: list[dict[str, Any]] = []
    totals = {
        "painting": 0.0, "masonry": 0.0, "plumbing": 0.0,
        "electrical": 0.0, "labor": 0.0,
        "minima": 0.0, "integral": 0.0,
    }
    total_area = 0.0

    for r in rooms or []:
        kind = str(r.get("kind") or "other")
        area = r.get("area_sqm") or 0
        breakdown = compute_room_labor(kind=kind, area_sqm=area or None, tier=tier)
        by_room.append(breakdown)
        for k in ("painting", "masonry", "plumbing", "electrical", "labor"):
            totals[k] += breakdown[k]
        totals["minima"] += breakdown["total_minima"]
        totals["integral"] += breakdown["total_integral"]
        total_area += breakdown["area_sqm"]

    totals = {k: _round2(v) for k, v in totals.items()}

    return {
        "rooms_count": len(by_room),
        "tier": tier,
        "rooms_aggregated_area_sqm": _round2(total_area),
        "by_room": by_room,
        "totals": totals,
        "valid_room_kinds": VALID_KINDS,
        "disclaimer": DISCLAIMER,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")

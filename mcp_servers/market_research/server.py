"""
MCP server: Market Research (comparables + valoración + ROI de reforma).

Tres tools:
  - find_comparables: devuelve 5-10 inmuebles similares en la zona.
  - estimate_market_value: valora un inmueble a partir de comparables.
  - compute_renovation_roi: revaloriza tras inversión en reforma.

Estado de comparables (MVP del challenge):
  Generador realista basado en mediana €/m² por provincia/distrito (datos públicos
  agregados de INE, Tinsa IMIE y Notarios CIEN). Cada comparable se construye con
  perturbaciones deterministas desde una semilla derivada de la coordenada, para
  que la misma zona devuelva siempre los mismos comparables (estable en demo y evals).

Roadmap (post-challenge): integración con proveedores oficiales con contrato
(Idealista Data, Tinsa API, microdatos INE). NO se contempla scraping de portales
— riesgo legal, ToS y de bloqueo. La interfaz de las tools no cambiará al enchufar
un proveedor real.

Diferencial vs producción Decomind: hoy (v1) el agente inmobiliario introduce
manualmente el precio/m² de la zona. Este MCP lo automatiza.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
from statistics import median
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_servers.market_research.data import (
    CONDITION_MULTIPLIER,
    antiquity_multiplier,
    resolve_base_price,
)
from mcp_servers.market_research.hedonic import value_breakdown
from mcp_servers._guardrails import (
    assess_source_agreement,
    validate_inputs,
    validate_valuation,
)

logger = logging.getLogger("mcp.market_research")

mcp = FastMCP("market-research")


# ---------- helpers ----------

def _seeded_rng(lat: float, lon: float) -> random.Random:
    """RNG determinista por coordenada — misma zona → mismos comparables."""
    key = f"{round(lat, 4)}:{round(lon, 4)}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return int(R * 2 * math.asin(math.sqrt(a)))


def _generate_synthetic_comparables(
    lat: float,
    lon: float,
    base_eur_sqm: float,
    property_type: str,
    radius_m: int,
    limit: int,
) -> list[dict[str, Any]]:
    rng = _seeded_rng(lat, lon)

    streets = [
        "Calle del Sol", "Calle Mayor", "Avenida de la Constitución", "Calle Real",
        "Calle Atocha", "Calle Goya", "Calle Serrano", "Calle Príncipe",
        "Calle Velázquez", "Calle Génova", "Calle Fuencarral", "Calle Hortaleza",
    ]
    rng.shuffle(streets)

    out: list[dict[str, Any]] = []
    for i in range(limit):
        # perturbación posicional dentro del radio
        bearing = rng.uniform(0, 2 * math.pi)
        dist = rng.uniform(50, radius_m)
        dlat = (dist * math.cos(bearing)) / 111_320
        dlon = (dist * math.sin(bearing)) / (111_320 * math.cos(math.radians(lat)))
        c_lat = lat + dlat
        c_lon = lon + dlon

        surface = rng.choice([55, 65, 72, 80, 88, 95, 105, 120])
        rooms = max(1, min(5, round(surface / 25)))
        year = rng.choice([1960, 1975, 1985, 1995, 2005, 2015, 2022])
        floor = rng.randint(0, 7)
        condition = rng.choices(
            ["nuevo", "buen_estado", "a_reformar"], weights=[0.15, 0.60, 0.25], k=1
        )[0]
        # precio ajustado por estado y antigüedad + ruido ±8%
        eur_sqm = base_eur_sqm * CONDITION_MULTIPLIER[condition] * antiquity_multiplier(year)
        eur_sqm *= rng.uniform(0.92, 1.08)
        price = round(eur_sqm * surface / 100) * 100  # redondeo a 100€

        out.append({
            "address": f"{streets[i % len(streets)]} {rng.randint(1, 200)}",
            "lat": round(c_lat, 6),
            "lon": round(c_lon, 6),
            "distance_m": _haversine_m(lat, lon, c_lat, c_lon),
            "property_type": property_type,
            "surface_m2": surface,
            "rooms": rooms,
            "floor": floor,
            "year_built": year,
            "condition": condition,
            "price_eur": price,
            "price_eur_per_m2": round(price / surface),
            "source": "synthetic-mvp",  # honest about the data source
        })
    return out


# ---------- tools ----------

@mcp.tool()
def find_comparables(
    lat: float,
    lon: float,
    province: str = "",
    district: str = "",
    municipality: str = "",
    property_type: str = "piso",
    radius_m: int = 500,
    limit: int = 8,
) -> dict[str, Any]:
    """Devuelve inmuebles similares (comparables) en la zona indicada.

    Mediana €/m² basada en datos oficiales del MITMA (Valor tasado de la
    vivienda) por municipio cuando es posible; fallback a estadísticas
    provinciales agregadas. Los comparables individuales (calle, m², precio)
    son sintéticos sobre esa base, etiquetados como tales en el campo `source`.

    Args:
        lat: Latitud del inmueble objetivo.
        lon: Longitud del inmueble objetivo.
        province: Provincia (ej. "Madrid").
        district: Distrito municipal (ej. "Centro"). Refina si existe
            multiplicador curado para esa (provincia, distrito).
        municipality: Municipio (ej. "Madrid", "Marbella"). Lookup directo
            en datos MITMA — es el dato más preciso si está disponible.
        property_type: "piso" | "atico" | "casa" | "local". Default "piso".
        radius_m: Radio de búsqueda en metros. Default 500.
        limit: Número de comparables a devolver. Default 8.

    Returns:
        {
          "count": int,
          "search": {lat, lon, province, district, municipality, radius_m},
          "median_price_eur_per_m2": float,
          "data_source": str,  # "mitma_municipal" | "curated_province" | "mitma_province" | "fallback"
          "comparables": [{address, lat, lon, distance_m, surface_m2, rooms, floor,
                          year_built, condition, price_eur, price_eur_per_m2,
                          source}, ...]
        }
    """
    limit = max(1, min(20, limit))

    # Fuente única de verdad: resolve_base_price devuelve (precio, etiqueta)
    base_eur_sqm, data_source = resolve_base_price(
        province=province or None,
        district=district or None,
        municipality=municipality or None,
    )

    comps = _generate_synthetic_comparables(
        lat=lat,
        lon=lon,
        base_eur_sqm=base_eur_sqm,
        property_type=property_type,
        radius_m=radius_m,
        limit=limit,
    )
    med = round(median(c["price_eur_per_m2"] for c in comps))

    return {
        "count": len(comps),
        "search": {
            "lat": lat, "lon": lon, "province": province,
            "district": district, "municipality": municipality,
            "radius_m": radius_m,
        },
        "median_price_eur_per_m2": med,
        "data_source": data_source,
        "comparables": comps,
    }


@mcp.tool()
def estimate_market_value(
    surface_m2: float,
    median_price_eur_per_m2: float,
    condition: str = "buen_estado",
    year_built: int = 0,
    floor: int = -999,
    has_elevator: bool = True,
    is_attic: bool = False,
    energy_rating: str = "",
    exterior: bool = True,
) -> dict[str, Any]:
    """Estima el valor de mercado con un modelo HEDÓNICO profesional.

    A diferencia de un multiplicador plano, ajusta el €/m² de la zona por 6
    factores que un tasador real considera: superficie (no lineal), estado,
    antigüedad, planta+ascensor, eficiencia energética y exterior/interior.

    Args:
        surface_m2: Superficie construida en m².
        median_price_eur_per_m2: €/m² mediano de la zona (de find_comparables).
        condition: "obra_nueva"|"reformado"|"buen_estado"|"a_reformar"|"ruina".
        year_built: Año de construcción. 0 = desconocido. (Idealmente del Catastro.)
        floor: Planta. 0 = bajo. -999 = desconocido (no ajusta).
        has_elevator: ¿Tiene ascensor? Relevante combinado con floor.
        is_attic: ¿Es ático? (premium).
        energy_rating: Letra "A".."G". "" = desconocido.
        exterior: ¿Exterior? False = interior (penaliza).

    Returns:
        {value_eur, value_eur_per_m2, base_eur_per_m2, combined_factor,
         factors{...}, model, assumptions}  — desglose 100% auditable.
    """
    # Guardrails de entrada: rechaza datos imposibles antes de calcular.
    input_errors = validate_inputs(
        surface_m2=surface_m2, year_built=year_built or None, condition=condition,
    )
    if input_errors:
        return {
            "error": "invalid_input",
            "validation_errors": input_errors,
            "value_eur": None,
        }

    bd = value_breakdown(
        surface_m2=surface_m2,
        base_eur_per_m2=median_price_eur_per_m2,
        condition=condition,
        year_built=year_built or None,
        floor=None if floor == -999 else floor,
        has_elevator=has_elevator,
        is_attic=is_attic,
        energy_rating=energy_rating or None,
        exterior=exterior,
    )

    # Guardrails de salida: marca si la valoración cae fuera de rangos de mercado.
    bd["warnings"] = validate_valuation(bd.get("value_eur"), bd.get("value_eur_per_m2"))
    bd["requires_review"] = bool(bd["warnings"])
    bd["assumptions"] = {
        "surface_m2": surface_m2,
        "median_price_eur_per_m2_input": median_price_eur_per_m2,
        "condition": condition,
        "year_built": year_built or None,
        "floor": None if floor == -999 else floor,
        "has_elevator": has_elevator,
        "is_attic": is_attic,
        "energy_rating": energy_rating or None,
        "exterior": exterior,
    }
    return bd


@mcp.tool()
def compute_renovation_roi(
    investment_eur: float,
    current_value_eur: float,
    post_reno_market_value_eur: float,
) -> dict[str, Any]:
    """Calcula el ROI de una reforma sobre el valor de mercado.

    Args:
        investment_eur: Coste estimado de la reforma.
        current_value_eur: Valor actual del inmueble (antes de reformar).
        post_reno_market_value_eur: Valor estimado tras la reforma.

    Returns:
        {investment, current_value, post_reno_value, gross_revaluation,
         net_gain, net_gain_pct, payback_ratio, recommendation}
    """
    gross = post_reno_market_value_eur - current_value_eur
    net = gross - investment_eur
    net_pct = round(100.0 * net / current_value_eur, 2) if current_value_eur else None
    payback = round(gross / investment_eur, 2) if investment_eur else None

    if net <= 0:
        rec = "no_recomendado"
    elif payback and payback >= 2.0:
        rec = "muy_recomendado"
    elif payback and payback >= 1.3:
        rec = "recomendado"
    else:
        rec = "marginal"

    return {
        "investment_eur": round(investment_eur, 2),
        "current_value_eur": round(current_value_eur, 2),
        "post_reno_value_eur": round(post_reno_market_value_eur, 2),
        "gross_revaluation_eur": round(gross, 2),
        "net_gain_eur": round(net, 2),
        "net_gain_pct_over_current": net_pct,
        "payback_ratio": payback,
        "recommendation": rec,
    }


@mcp.tool()
def check_source_agreement(
    notariado_price_eur_per_m2: float = 0,
    mitma_price_eur_per_m2: float = 0,
) -> dict[str, Any]:
    """Compara las dos fuentes oficiales de precio (Notariado real vs MITMA
    tasación) y evalúa su concordancia.

    Guardrail de calidad: si las fuentes divergen demasiado (transacción real
    muy lejos de la tasación), marca requires_review=True para que el agente
    inmobiliario lo valide antes de fijar precio, en vez de dar un número a ciegas.

    Args:
        notariado_price_eur_per_m2: €/m² real de transacción (del Notariado).
        mitma_price_eur_per_m2: €/m² tasado (de MITMA).

    Returns:
        {convergence_pct, agreement (high/moderate/low/single_source),
         requires_review, note}
    """
    return assess_source_agreement(
        notariado_price_eur_per_m2 or None, mitma_price_eur_per_m2 or None,
    )


if __name__ == "__main__":
    from mcp_servers._runtime import run_server
    run_server(mcp)

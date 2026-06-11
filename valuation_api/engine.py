"""
Motor de valoración — orquestación DETERMINISTA por código (sin LLM).

`run_valuation()` encadena las mismas funciones que el agente del challenge usa
como tools, pero llamadas directamente como Python (sin MCP/stdio ni Gemini).
Resultado: un JSON estable y reproducible, ideal para integración B2B (Decomind
Azure lo consume por HTTP).

Pipeline:
  geocoding -> catastro (año oficial) -> notariado (precio real por CP)
            -> MITMA (tasación, 2ª fuente) -> modelo hedónico -> triangulación
            -> [reforma + ROI opcional]

Reutiliza la lógica ya escrita y testeada (evals 100%) en mcp_servers/.
"""

from __future__ import annotations

from typing import Any

from mcp_servers.geocoding.server import geocode_address
from mcp_servers.catastro.server import catastro_lookup
from mcp_servers.notariado.server import notariado_price
from mcp_servers.market_research.server import (
    find_comparables,
    estimate_market_value,
    compute_renovation_roi,
    check_source_agreement,
)
from mcp_servers.renovation.server import estimate_renovation_plan

_FLOOR_UNKNOWN = -999


def run_valuation(
    address: str,
    locality: str = "",
    province: str = "",
    postal_code: str = "",
    surface_m2: float = 0,
    condition: str = "buen_estado",
    year_built: int = 0,
    floor: int | None = None,
    has_elevator: bool = True,
    is_attic: bool = False,
    energy_rating: str = "",
    exterior: bool = True,
    rooms: list[dict[str, Any]] | None = None,
    renovation_tier: str = "standard",
    include_renovation: bool = True,
) -> dict[str, Any]:
    """Valora un inmueble de forma determinista. Devuelve un dict estructurado.

    Args:
        address: Calle y número.
        locality / province / postal_code: ubicación (postal_code muy recomendado).
        surface_m2: superficie construida.
        condition: estado (a_reformar/buen_estado/reformado/obra_nueva/ruina).
        year_built: año (0 = usar el oficial del Catastro si está).
        floor / has_elevator / is_attic / energy_rating / exterior: factores
            hedónicos (opcionales; si no se conocen se usan neutros).
        rooms: lista de estancias para presupuesto de reforma (opcional).
        renovation_tier: economy/standard/premium.
        include_renovation: si False, omite reforma+ROI (solo valoración).

    Returns:
        dict con found, location, cadastral, valuation, sources, [renovation, roi].
    """
    # 1. Geocoding
    geo = geocode_address(
        address=address, locality=locality, province=province,
        postal_code=postal_code,
    )
    if not geo.get("found"):
        return {"found": False, "reason": "address_not_found", "input_address": address}

    lat = float(geo.get("lat") or 0)
    lon = float(geo.get("lon") or 0)
    muni = geo.get("municipality") or locality
    prov = geo.get("province") or province
    distr = geo.get("city_district") or ""
    cp = (postal_code or geo.get("postcode") or "").strip()

    # 2. Catastro (año oficial — mejor que el del usuario)
    cat = catastro_lookup(lat, lon) if (lat and lon) else {"found": False}
    official_year = cat.get("year_built")
    year = official_year or year_built or 0

    # 3. Notariado (precio REAL de transacción por CP, fuente primaria)
    nota = notariado_price(postal_code=cp, municipality=muni, province=prov)
    nota_price = nota.get("price_eur_per_m2") if nota.get("found") else None

    # 4. MITMA (find_comparables -> mediana tasada, 2ª fuente)
    comps = find_comparables(
        lat=lat, lon=lon, province=prov, municipality=muni, district=distr,
    )
    mitma_price = comps.get("median_price_eur_per_m2")

    # 5. Precio base: Notariado preferente, MITMA fallback
    base_price = nota_price or mitma_price or 1800.0

    # 6. Valoración hedónica (valor actual)
    val = estimate_market_value(
        surface_m2=surface_m2,
        median_price_eur_per_m2=base_price,
        condition=condition,
        year_built=year or 0,
        floor=_FLOOR_UNKNOWN if floor is None else floor,
        has_elevator=has_elevator,
        is_attic=is_attic,
        energy_rating=energy_rating or "",
        exterior=exterior,
    )
    if val.get("error"):
        return {"found": False, "reason": val.get("error"),
                "validation_errors": val.get("validation_errors")}
    current_value = val.get("value_eur")

    # 7. Triangulación de fuentes (convergencia + flag revisión)
    agreement = check_source_agreement(nota_price or 0, mitma_price or 0)

    result: dict[str, Any] = {
        "found": True,
        "address": geo.get("display_name") or address,
        "location": {
            "municipality": muni, "province": prov, "district": distr,
            "postal_code": cp, "lat": lat, "lon": lon,
        },
        "cadastral": {
            "found": bool(cat.get("found")),
            "reference": cat.get("cadastral_reference"),
            "official_year_built": official_year,
            "use": cat.get("primary_use"),
        },
        "valuation": {
            "current_value_eur": current_value,
            "value_eur_per_m2": val.get("value_eur_per_m2"),
            "base_eur_per_m2": val.get("base_eur_per_m2"),
            "combined_factor": val.get("combined_factor"),
            "hedonic_factors": val.get("factors"),
            "warnings": val.get("warnings", []),
            "requires_review": val.get("requires_review", False),
        },
        "sources": {
            "notariado": {
                "price_eur_per_m2": nota_price,
                "num_transactions": nota.get("num_transactions"),
                "level": nota.get("level"),
                "is_estimated": nota.get("is_estimated"),
            } if nota.get("found") else None,
            "mitma": {
                "price_eur_per_m2": mitma_price,
                "data_source": comps.get("data_source"),
            },
            "agreement": agreement,
        },
    }

    # 8. Reforma + ROI (opcional)
    if include_renovation and rooms:
        plan = estimate_renovation_plan(rooms=rooms, tier=renovation_tier)
        reno_total = (plan.get("totals") or {}).get("integral", 0)

        val_post = estimate_market_value(
            surface_m2=surface_m2,
            median_price_eur_per_m2=base_price,
            condition="buen_estado",
            year_built=year or 0,
            floor=_FLOOR_UNKNOWN if floor is None else floor,
            has_elevator=has_elevator,
            is_attic=is_attic,
            energy_rating=energy_rating or "",
            exterior=exterior,
        )
        post_value = val_post.get("value_eur")
        roi = compute_renovation_roi(
            investment_eur=reno_total,
            current_value_eur=current_value,
            post_reno_market_value_eur=post_value,
        )
        result["renovation"] = {
            "tier": renovation_tier,
            "total_integral_eur": reno_total,
            "by_room": plan.get("by_room"),
            "post_reno_value_eur": post_value,
        }
        result["roi"] = roi

    return result

"""
Motor de valoración — orquestación DETERMINISTA por código (sin LLM).

`run_valuation()` encadena las mismas funciones que el agente del challenge usa
como tools, pero llamadas directamente como Python (sin MCP/stdio ni Gemini).
Resultado: un JSON estable y reproducible, ideal para integración B2B (Decomind
Azure lo consume por HTTP).

Pipeline:
  [features de anuncio -> parser] -> geocoding -> catastro (año oficial)
            -> notariado (precio real por CP) -> MITMA (tasación, 2ª fuente)
            -> modelo hedónico v2 -> triangulación -> [reforma + ROI opcional]

Si llegan `features` (lista de características del Clipper/Idealista) se
parsean de forma determinista y rellenan SOLO los campos que el llamador no
haya dado explícitamente. La respuesta declara qué se derivó del anuncio
(`derived_from_features`) y qué quedó desconocido con factor neutro
(`assumed_neutral_fields`) — sin suposiciones optimistas silenciosas.

Reutiliza la lógica ya escrita y testeada (evals 100%) en mcp_servers/.
"""

from __future__ import annotations

import re
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
from mcp_servers.market_research.features_parser import parse_property_features
from mcp_servers.renovation.server import estimate_renovation_plan
from mcp_servers._guardrails import (
    PROVINCE_ALIASES_BY_CP_PREFIX,
    _norm_province,
    cp_matches_province,
)

_FLOOR_UNKNOWN = -999

# Títulos de anuncio que llegan como "dirección": "Piso en venta en Calle X",
# "Ático en alquiler en Av. Y"... Nominatim no los geocodifica.
_LISTING_TITLE_RE = re.compile(
    r"^\s*(?:piso|atico|ático|casa|chalet|adosado|pareado|duplex|dúplex|"
    r"apartamento|estudio|loft|bajo|vivienda|finca|local)\s+"
    r"(?:en\s+(?:venta|alquiler)\s+)?en\s+(.+)$",
    re.IGNORECASE,
)


def _clean_listing_address(address: str) -> str:
    """Extrae la calle de un título de anuncio. "Piso en venta en Calle
    Cervantes, Monte Alto" → "Calle Cervantes". Conserva el número aunque
    venga tras coma ("Calle Real, 12")."""
    a = (address or "").strip()
    m = _LISTING_TITLE_RE.match(a)
    if m:
        a = m.group(1).strip()
    parts = [p.strip() for p in a.split(",") if p.strip()]
    if len(parts) > 1 and parts[1][:1].isdigit():
        return f"{parts[0]} {parts[1]}"  # "Calle Real, 12" → "Calle Real 12"
    return parts[0] if parts else a


def _geocode_with_fallback(
    address: str, locality: str, province: str, postal_code: str,
) -> tuple[dict[str, Any], str | None]:
    """Geocoding con degradación progresiva. Una provincia o CP equivocados
    (datos arrastrados de otra vivienda) envenenan la query de Nominatim,
    así que los intentos van soltando lastre:
      calle tal cual → título limpiado → calle sin provincia → calle sin
      provincia ni CP → nivel zona (localidad) → zona sin provincia ni CP.
    Devuelve (geo, precision): "street" | "locality" | None (no encontrado)."""
    raw = (address or "").strip()
    cleaned = _clean_listing_address(raw)
    best = cleaned or raw
    cp = (postal_code or "").strip()

    attempts: list[tuple[str, str, str, str]] = []  # (addr, prov, cp, precision)
    if raw:
        attempts.append((raw, province, cp, "street"))
    if cleaned and cleaned != raw:
        attempts.append((cleaned, province, cp, "street"))
    if best and province:
        attempts.append((best, "", cp, "street"))   # provincia quizá errónea
    if best and cp:
        attempts.append((best, "", "", "street"))   # CP quizá erróneo
    if locality or cp:
        zone = locality or cp
        attempts.append((zone, province, cp, "locality"))
        attempts.append((zone, "", "", "locality"))

    seen: set[tuple[str, str, str]] = set()
    for addr, prov, pc, precision in attempts:
        key = (addr, prov, pc)
        if not addr or key in seen:
            continue
        seen.add(key)
        geo = geocode_address(address=addr, locality=locality,
                              province=prov, postal_code=pc)
        if geo.get("found"):
            return geo, precision
    return {"found": False}, None


def _same_province(a: str, b: str) -> bool | None:
    """¿Son la misma provincia? Tolera variantes ("La Coruña"/"A Coruña",
    "Castellón"/"Castelló"). None si algún nombre falta o no se reconoce."""
    na, nb = _norm_province(a), _norm_province(b)
    if not na or not nb:
        return None
    if na == nb:
        return True
    for aliases in PROVINCE_ALIASES_BY_CP_PREFIX.values():
        if na in aliases:
            return nb in aliases
    return None


def resolve_location(
    address: str = "", locality: str = "", province: str = "",
    postal_code: str = "",
) -> dict[str, Any]:
    """Resuelve la ubicación SIN valorar (para prefill de formularios):
    geocoding tolerante a datos mezclados + provincia/CP coherentes.
    El CP solo se devuelve si es fiable (del usuario validado o del geocoder
    a nivel calle)."""
    user_cp = (postal_code or "").strip()
    if user_cp and province and cp_matches_province(user_cp, province) is False:
        user_cp = ""
    geo, precision = _geocode_with_fallback(address, locality, province, user_cp)
    if not geo.get("found"):
        return {"found": False}
    geo_prov = geo.get("province") or ""
    prov = geo_prov or province
    geo_cp = ((geo.get("postcode") or "") if precision == "street" else "").strip()
    cp = (user_cp or geo_cp or "").strip()
    if cp and cp_matches_province(cp, prov) is False:
        cp = (geo_cp if geo_cp and cp_matches_province(geo_cp, prov) is not False
              else "")
    return {
        "found": True,
        "precision": precision,
        "municipality": geo.get("municipality") or locality,
        "province": prov,
        "postal_code": cp,
        "display_name": geo.get("display_name"),
    }


def _tri(value: bool | None) -> int:
    """bool|None → sentinel int del tool MCP (-1 desconocido, 0 no, 1 sí)."""
    return -1 if value is None else int(bool(value))


def run_valuation(
    address: str,
    locality: str = "",
    province: str = "",
    postal_code: str = "",
    surface_m2: float = 0,
    condition: str = "",
    year_built: int = 0,
    floor: int | None = None,
    has_elevator: bool | None = None,
    is_attic: bool = False,
    energy_rating: str = "",
    exterior: bool | None = None,
    orientation: str = "",
    bedrooms: int = 0,
    bathrooms: int = 0,
    has_terrace: bool = False,
    has_garage: bool = False,
    has_storage_room: bool = False,
    has_pool: bool = False,
    features: list[str] | None = None,
    description: str = "",
    rooms: list[dict[str, Any]] | None = None,
    renovation_tier: str = "standard",
    include_renovation: bool = True,
) -> dict[str, Any]:
    """Valora un inmueble de forma determinista. Devuelve un dict estructurado.

    Args:
        address: Calle y número.
        locality / province / postal_code: ubicación (postal_code muy recomendado).
        surface_m2: superficie construida (0 = intentar derivarla de `features`).
        condition: estado (a_reformar/buen_estado/reformado/obra_nueva/ruina).
            "" = desconocido: se toma de `features` o, en último caso,
            'buen_estado' (y se declara como asumido).
        year_built: año (0 = usar el oficial del Catastro si está).
        floor / has_elevator / is_attic / energy_rating / exterior / orientation
            / bedrooms / bathrooms / has_terrace / has_garage / has_storage_room
            / has_pool: factores hedónicos. None/0/""/False = desconocido →
            factor neutro (nunca se asume optimistamente).
        features: características del anuncio (Clipper/Idealista) — rellenan
            los campos no informados, vía parser determinista.
        description: texto libre del anuncio (complemento del parser).
        rooms: lista de estancias para presupuesto de reforma (opcional).
        renovation_tier: economy/standard/premium.
        include_renovation: si False, omite reforma+ROI (solo valoración).

    Returns:
        dict con found, location, cadastral, valuation (incl. hedonic_factors,
        assumed_neutral_fields), property_inputs, derived_from_features,
        sources, [renovation, roi].
    """
    # 0. Características del anuncio → inputs (solo huecos no informados)
    derived: dict[str, Any] = {}
    if features or (description and description.strip()):
        parsed = parse_property_features(features, description).get("fields", {})

        def fill(name: str, current: Any, empty: Any) -> Any:
            if current == empty and name in parsed and parsed[name] != empty:
                derived[name] = parsed[name]
                return parsed[name]
            return current

        surface_m2 = fill("surface_m2", surface_m2, 0)
        condition = fill("condition", condition, "")
        floor = fill("floor", floor, None)
        has_elevator = fill("has_elevator", has_elevator, None)
        is_attic = fill("is_attic", is_attic, False)
        energy_rating = fill("energy_rating", energy_rating, "")
        exterior = fill("exterior", exterior, None)
        orientation = fill("orientation", orientation, "")
        bedrooms = fill("bedrooms", bedrooms, 0)
        bathrooms = fill("bathrooms", bathrooms, 0)
        has_terrace = fill("has_terrace", has_terrace, False)
        has_garage = fill("has_garage", has_garage, False)
        has_storage_room = fill("has_storage_room", has_storage_room, False)
        has_pool = fill("has_pool", has_pool, False)
        if not year_built and parsed.get("year_built"):
            derived["year_built"] = parsed["year_built"]
            year_built = parsed["year_built"]

    condition_assumed = not condition
    condition = condition or "buen_estado"

    # 0b. Coherencia CP ↔ provincia ANTES de geocodificar: un CP de otra
    # provincia contamina la query y, peor, llevaría al Notariado a devolver
    # precios de otra provincia.
    pre_warnings: list[str] = []
    user_cp = (postal_code or "").strip()
    if user_cp and province and cp_matches_province(user_cp, province) is False:
        pre_warnings.append(
            f"El código postal {user_cp} no corresponde a la provincia "
            f"{province}: se ha ignorado.")
        user_cp = ""

    # 1. Geocoding (con fallback: título de anuncio limpiado → sin provincia
    # → nivel zona)
    geo, precision = _geocode_with_fallback(address, locality, province, user_cp)
    if not geo.get("found"):
        return {"found": False, "reason": "address_not_found", "input_address": address}

    lat = float(geo.get("lat") or 0)
    lon = float(geo.get("lon") or 0)
    muni = geo.get("municipality") or locality
    geo_prov = geo.get("province") or ""
    prov = geo_prov or province
    if province and _same_province(province, geo_prov) is False:
        pre_warnings.append(
            f"La provincia indicada ({province}) no coincide con la ubicación "
            f"encontrada ({geo_prov}): se ha usado {geo_prov}.")
    distr = geo.get("city_district") or ""
    # A nivel zona el postcode del geocoder es el del centro del municipio:
    # mejor sin CP (el Notariado degrada limpio a nivel municipio).
    geo_cp = ((geo.get("postcode") or "") if precision == "street" else "").strip()
    cp = (user_cp or geo_cp or "").strip()
    if cp and cp_matches_province(cp, prov) is False:
        # Si el geocoder encontró la dirección, su CP es el bueno: recupéralo.
        fallback_cp = (geo_cp if geo_cp and geo_cp != cp
                       and cp_matches_province(geo_cp, prov) is not False else "")
        if fallback_cp:
            pre_warnings.append(
                f"El código postal {cp} no corresponde a {prov}: se ha usado "
                f"el {fallback_cp} de la dirección localizada.")
        else:
            pre_warnings.append(
                f"El código postal {cp} no corresponde a {prov}: se ha "
                f"ignorado (precio a nivel de municipio).")
        cp = fallback_cp

    # 2. Catastro (año oficial). Solo con dirección exacta: a nivel zona las
    # coords son el centro del municipio y devolverían la parcela equivocada.
    cat = (catastro_lookup(lat, lon)
           if (lat and lon and precision == "street") else {"found": False})
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

    hedonic_kwargs = dict(
        floor=_FLOOR_UNKNOWN if floor is None else floor,
        has_elevator=_tri(has_elevator),
        is_attic=is_attic,
        energy_rating=energy_rating or "",
        exterior=_tri(exterior),
        orientation=orientation or "",
        bedrooms=bedrooms or 0,
        bathrooms=bathrooms or 0,
        has_terrace=has_terrace,
        has_garage=has_garage,
        has_storage_room=has_storage_room,
        has_pool=has_pool,
    )

    # 6. Valoración hedónica (valor actual)
    val = estimate_market_value(
        surface_m2=surface_m2,
        median_price_eur_per_m2=base_price,
        condition=condition,
        year_built=year or 0,
        **hedonic_kwargs,
    )
    if val.get("error"):
        return {"found": False, "reason": val.get("error"),
                "validation_errors": val.get("validation_errors")}
    current_value = val.get("value_eur")

    # Campos sin dato → factor neutro aplicado. El frontend debe enseñarlos
    # ("no considerado: indícalo para afinar") en vez de fingir precisión.
    assumed = list(val.get("unknown_inputs") or [])
    if not condition_assumed and "condition" in assumed:
        assumed.remove("condition")
    if condition_assumed and "condition" not in assumed:
        assumed.append("condition")

    # 7. Triangulación de fuentes (convergencia + flag revisión)
    agreement = check_source_agreement(nota_price or 0, mitma_price or 0)

    warnings = pre_warnings + list(val.get("warnings", []))
    if precision == "locality":
        warnings.append(
            "Dirección no localizada con exactitud: valoración a nivel de "
            "zona (sin año oficial del Catastro). Indica calle y número "
            "reales para afinar.")

    result: dict[str, Any] = {
        "found": True,
        "address": geo.get("display_name") or address,
        "location": {
            "municipality": muni, "province": prov, "district": distr,
            "postal_code": cp, "lat": lat, "lon": lon,
            "precision": precision,
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
            "model": val.get("model"),
            "assumed_neutral_fields": assumed,
            "warnings": warnings,
            "requires_review": val.get("requires_review", False),
        },
        # Inputs finales usados (tras anuncio + Catastro) — auditable en UI.
        "property_inputs": {
            "surface_m2": surface_m2,
            "condition": condition,
            "year_built": year or None,
            "floor": floor,
            "has_elevator": has_elevator,
            "is_attic": is_attic,
            "energy_rating": energy_rating or None,
            "exterior": exterior,
            "orientation": orientation or None,
            "bedrooms": bedrooms or None,
            "bathrooms": bathrooms or None,
            "has_terrace": has_terrace,
            "has_garage": has_garage,
            "has_storage_room": has_storage_room,
            "has_pool": has_pool,
        },
        "derived_from_features": derived or None,
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
            **hedonic_kwargs,
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

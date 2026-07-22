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

import math
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
from mcp_servers.market_research.data_ipv import annual_trend as ipv_annual_trend
from mcp_servers.market_research.data_mitma import MITMA_QUARTER
from mcp_servers.renovation.server import estimate_renovation_plan
from mcp_servers.seccion_censal.server import (
    seccion_lookup,
    seccion_signal_gradient,
    stock_age_year,
)
from mcp_servers.zona_valor.server import zona_valor_gradient
from mcp_servers._guardrails import (
    PROVINCE_ALIASES_BY_CP_PREFIX,
    _norm_province,
    cp_matches_province,
)

# Versión del MODELO de valoración (lógica/calibraciones, no la API HTTP).
# Bump manual en cada cambio que altere resultados; queda persistida junto a
# cada valoración guardada para poder interpretar históricos.
MODEL_VERSION = "valuation-v2.8.0"

_FLOOR_UNKNOWN = -999
# Lag efectivo del snapshot del Notariado (ventana de agregación ~12 meses →
# punto medio ~6m + retardo de publicación ~3m) para la reexpresión con el IPV.
_TREND_LAG_YEARS = 0.75
# Cota del gradiente de micro-ubicación COMBINADO (ponencia × sección censal).
_LOCATION_BOUND = 0.30


def _combine_gradients(gradients: list[float | None]) -> float:
    """Media geométrica de los gradientes disponibles, acotada. Función pura.

    Cada señal ya viene amortiguada/acotada por su módulo; la media geométrica
    hace que dos señales discrepantes se moderen entre sí (ponencia vieja que
    dice -8% + mercado actual que dice +10% → ~+1%).
    """
    vals = [g for g in gradients if g and g > 0]
    if not vals:
        return 1.0
    g = math.exp(sum(math.log(v) for v in vals) / len(vals))
    g = max(1 - _LOCATION_BOUND, min(1 + _LOCATION_BOUND, g))
    return round(g, 4)

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
    "Castellón"/"Castelló"). None si algún nombre falta o NO SE RECONOCE —
    los geocoders a veces devuelven la CCAA ("Comunidad de Madrid") o la
    comarca, y ante eso no se afirma discrepancia."""
    na, nb = _norm_province(a), _norm_province(b)
    if not na or not nb:
        return None
    if na == nb:
        return True
    known_a = known_b = False
    for aliases in PROVINCE_ALIASES_BY_CP_PREFIX.values():
        in_a, in_b = na in aliases, nb in aliases
        if in_a and in_b:
            return True
        known_a = known_a or in_a
        known_b = known_b or in_b
    return False if (known_a and known_b) else None


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


_BASE_DISPERSION = 0.08  # dispersión intra-zona (un inmueble vs la media de su segmento)


def info_dispersion(
    base: float = _BASE_DISPERSION, *,
    num_transactions: int = 0,
    location_signals_agree: bool | None = None,
    unknown_count: int = 0,
) -> float:
    """Dispersión base SENSIBLE A LA INFORMACIÓN disponible. Función pura.

    Una banda honesta se estrecha cuando hay más evidencia y se ensancha
    cuando falta: muchas compraventas locales (-), las dos señales de
    micro-ubicación coinciden (-) o discrepan (+), y cada característica
    sin informar más allá de dos suma incertidumbre (+). Acotada [5%, 12%];
    el gap inter-fuente se suma aparte en confidence_band.
    """
    d = base
    if num_transactions >= 300:
        d -= 0.02
    elif num_transactions >= 100:
        d -= 0.01
    elif 0 < num_transactions < 30:
        d += 0.01
    if location_signals_agree is True:
        d -= 0.01
    elif location_signals_agree is False:
        d += 0.01
    d += 0.005 * max(0, unknown_count - 2)
    return min(max(d, 0.05), 0.12)


def confidence_band(
    center_m2: float | None, surface_m2: float,
    nota_price: float | None, mitma_price: float | None,
    base: float = _BASE_DISPERSION,
) -> tuple[dict[str, Any] | None, float | None]:
    """Banda de confianza SIMÉTRICA sobre el valor recomendado.

    Ancho = dispersión base + medio gap inter-fuente (Notariado vs MITMA): si las
    dos fuentes oficiales convergen, la banda se estrecha; si divergen, se
    ensancha. Una sola fuente → algo más ancha (sin triangulación). El central
    SIEMPRE cae dentro (la banda es simétrica sobre él). Devuelve (interval, half)
    o (None, None) si faltan datos para construirla.
    """
    if not (center_m2 and surface_m2):
        return None, None
    half = base
    if nota_price and mitma_price:
        half += abs(nota_price - mitma_price) / max(nota_price, mitma_price) / 2
    else:
        half += 0.06
    half = min(half, 0.25)   # techo: nunca una banda absurda
    interval = {
        "low_eur": round(center_m2 * (1 - half) * surface_m2 / 100) * 100,
        "high_eur": round(center_m2 * (1 + half) * surface_m2 / 100) * 100,
        "low_eur_per_m2": round(center_m2 * (1 - half)),
        "high_eur_per_m2": round(center_m2 * (1 + half)),
    }
    return interval, half


def run_valuation(
    address: str,
    locality: str = "",
    province: str = "",
    postal_code: str = "",
    surface_m2: float = 0,
    condition: str = "",
    property_type: str = "",
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
        property_type: piso/atico/casa/chalet/adosado/pareado/unifamiliar.
            "" = no segmentar (Notariado agregado, comportamiento histórico).
            Si llega, el Notariado consulta inmuebles SIMILARES (pisos vs
            unifamiliares; obra nueva vs usada según `condition`).
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

    # 3. Notariado (precio REAL de transacción por CP, fuente primaria).
    # Segmento del inmueble para pedir el precio de SIMILARES (no el agregado de
    # todas las viviendas). OPT-IN: sin property_type → sin segmento → mismo
    # comportamiento histórico (importante: el Dossier ROI no pasa tipo).
    _UNIFAM = {"casa", "chalet", "adosado", "pareado", "unifamiliar"}
    if property_type:
        property_class = "unifamiliar" if property_type.lower() in _UNIFAM else "piso"
        construction = "nueva" if condition == "obra_nueva" else "usada"
    else:
        property_class = construction = ""
    nota = notariado_price(postal_code=cp, municipality=muni, province=prov,
                           property_class=property_class, construction=construction)
    nota_price = nota.get("price_eur_per_m2") if nota.get("found") else None

    # 4. MITMA (find_comparables -> mediana tasada, 2ª fuente).
    # data_source=="fallback" = resolve_base_price agotó MITMA municipio/
    # provincia y devolvió el 1800 €/m² fijo de España: eso NO es evidencia,
    # es una invención plausible — se descarta para la abstención de abajo.
    comps = find_comparables(
        lat=lat, lon=lon, province=prov, municipality=muni, district=distr,
    )
    mitma_price = (comps.get("median_price_eur_per_m2")
                   if comps.get("data_source") != "fallback" else None)

    # 5. Precio base: Notariado preferente, MITMA fallback. Sin NINGUNA fuente
    # oficial NO se inventa un €/m² (antes: 1800 fijo → cifra plausible pero
    # potencialmente muy errónea). Abstención explícita: found=false con
    # reason=insufficient_evidence — NO es un error, es "sin datos aquí".
    base_price = nota_price or mitma_price
    if not base_price:
        return {
            "found": False,
            "reason": "insufficient_evidence",
            "message": ("No hay compraventas del Notariado ni tasaciones MITMA "
                        "suficientes en esta zona para una valoración fiable."),
            "location": {
                "municipality": muni, "province": prov, "district": distr,
                "postal_code": cp, "precision": precision,
            },
            "model_version": MODEL_VERSION,
        }

    # 5b. Reexpresión temporal a "hoy" (IPV del INE por CCAA y tipo). El
    # snapshot del Notariado agrega ~12 meses de compraventas → su punto medio
    # queda ~9 meses atrás; con el mercado a doble dígito anual eso es un sesgo
    # a la baja sistemático. Se aplica a la BASE (también la lee el Dossier
    # ROI: el €/m² de zona reexpresado a hoy es el correcto para ambos).
    # Fail-safe: sin red/sin dato → no-op. ponytail: lag 0.75 años estimado
    # (ventana 12m + retardo de publicación); calibrar con cierres.
    temporal_adjustment: dict[str, Any] = {"applied": False}
    if nota_price:
        try:
            trend = ipv_annual_trend(prov, construction)
        except Exception:
            trend = None
        if trend and abs(trend.get("annual_pct") or 0) >= 1.0:
            t_factor = (1 + trend["annual_pct"] / 100) ** _TREND_LAG_YEARS
            base_price = round(base_price * t_factor, 1)
            temporal_adjustment = {
                "applied": True,
                "factor": round(t_factor, 4),
                "pct": round((t_factor - 1) * 100, 1),
                "ipv_annual_pct": trend["annual_pct"],
                "period": trend.get("period"),
                # Frescura de la serie: si el INE rota de base (como la 25171
                # congelada en 2025T4), stale=true delata el dato rancio en
                # vez de envejecer en silencio.
                "data_as_of": trend.get("data_as_of"),
                "stale": bool(trend.get("stale")),
                "scope": trend.get("scope"),
                "lag_years": _TREND_LAG_YEARS,
                "source": "ine_ipv",
            }

    # v2.8.0 — doble conteo de obra nueva: si la base del Notariado ya viene
    # del segmento 'nueva' (más caro de por sí), aplicar además la prima de
    # estado la contaría DOS veces (matriz de sesgos 2026-07: obra nueva
    # +18.5%, BCN +32%). Con base segmentada 'nueva' el estado pasa a neutro.
    hedonic_condition = condition
    if (condition == "obra_nueva" and nota_price
            and (nota.get("segment") or {}).get("construction") == "nueva"):
        hedonic_condition = "buen_estado"

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

    # 5c. Sección censal del punto (una sola llamada al INE; se reutiliza para
    # la antigüedad relativa y para el gradiente de mercado de 6a).
    seccion = {"found": False}
    if precision == "street" and lat and lon:
        try:
            seccion = seccion_lookup(lat, lon)
        except Exception:
            seccion = {"found": False}
    zone_year = (stock_age_year(seccion.get("cusec"), seccion.get("cumun"))
                 if seccion.get("found") else None)

    # 6. Valoración hedónica (valor actual). Con precio del Notariado, su
    # superficie_media activa la curva de superficie RELATIVA (un piso de 50 m²
    # en una zona de media 94 m² cotiza €/m² muy por encima de la mediana); el
    # año típico del parque de la sección (Censo/INE) activa la antigüedad
    # RELATIVA (edificio del 2000 en barrio de los 70 = premium).
    zone_avg_surface = (nota.get("avg_surface_m2") or 0) if nota.get("found") else 0
    val = estimate_market_value(
        surface_m2=surface_m2,
        median_price_eur_per_m2=base_price,
        condition=hedonic_condition,
        year_built=year or 0,
        zone_avg_surface_m2=zone_avg_surface if nota_price else 0,
        zone_typical_year=zone_year or 0,
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

    # 6a. Ajuste FINO de ubicación dentro del CP (zona de valor del Catastro).
    # El Notariado solo baja a CP: dentro del CP todas las calles cobran igual.
    # DOS señales independientes de micro-ubicación, combinadas por media
    # geométrica (cada una ya viene amortiguada y acotada por su módulo):
    #   - Ponencia catastral (zona de valor): estructural, pero puede estar vieja.
    #   - Sección censal (alquiler SERPAVI + renta INE): mercado ACTUAL — corrige
    #     ponencias desactualizadas y cubre donde no hay ponencia (forales).
    # Solo con dirección exacta (a nivel zona el punto es el centroide del
    # municipio). NO toca `base_eur_per_m2` (el Dossier ROI lo lee y debe seguir
    # siendo el €/m² de zona). No-op donde no hay cobertura de ninguna.
    value_per_m2 = val.get("value_eur_per_m2")
    location_adjustment: dict[str, Any] = {"applied": False}
    if precision == "street" and lat and lon and value_per_m2:
        try:
            grad = zona_valor_gradient(lat=lat, lon=lon)
        except Exception:
            grad = {"found": False, "gradient": 1.0}
        try:
            sec = seccion_signal_gradient(
                lat=lat, lon=lon,
                cusec=seccion.get("cusec") or "", cumun=seccion.get("cumun") or "")
        except Exception:
            sec = {"found": False, "gradient": 1.0}
        g = _combine_gradients([
            grad.get("gradient") if grad.get("found") else None,
            sec.get("gradient") if sec.get("found") else None,
        ])
        if g != 1.0:
            value_per_m2 = round(value_per_m2 * g)
            current_value = round(current_value * g)
            components = {}
            if grad.get("found"):
                components["catastro_zona_valor"] = round((grad["gradient"] - 1) * 100, 1)
            if sec.get("found"):
                components["seccion_censal"] = round((sec["gradient"] - 1) * 100, 1)
            location_adjustment = {
                "applied": True,
                "gradient": g,
                "pct": round((g - 1) * 100, 1),
                "zone_code": grad.get("zone_code"),
                "neighborhood_mean_eur_m2": grad.get("neighborhood_mean"),
                "cusec": sec.get("cusec"),
                "components": components,
                "source": "+".join(components.keys()),
            }

    # 6b. Banda de confianza centrada en el valor recomendado (ya con el ajuste de
    # ubicación); el ancho refleja la incertidumbre REAL: dispersión base sensible
    # a la información (nº de ventas, acuerdo entre señales de ubicación, campos
    # sin informar) + desacuerdo entre fuentes.
    # ponytail: upgrade final = dispersión medida con cierres/comparables reales.
    comps_pcts = list((location_adjustment.get("components") or {}).values())
    signals_agree = (abs(comps_pcts[0] - comps_pcts[1]) <= 8.0
                     if len(comps_pcts) == 2 else None)
    interval, band_half = confidence_band(
        value_per_m2, surface_m2, nota_price, mitma_price,
        base=info_dispersion(
            num_transactions=(nota.get("num_transactions") or 0) if nota.get("found") else 0,
            location_signals_agree=signals_agree,
            unknown_count=len(assumed),
        ))
    if interval is not None:
        # ponytail: el central siempre cae dentro (banda simétrica sobre el valor)
        assert interval["low_eur"] <= current_value <= interval["high_eur"], \
            (interval, current_value)

    # 7. Triangulación de fuentes (convergencia + flag revisión)
    agreement = check_source_agreement(nota_price or 0, mitma_price or 0)

    # 7b. Confianza de la valoración: un único veredicto (Alta/Media/Baja), no
    # campos crudos sueltos. El frontend lo muestra como sello junto al precio.
    _LV = {"high": "alta", "moderate": "media", "low": "baja", "single_source": "media"}
    conf_level = _LV.get(agreement.get("agreement"), "media")
    # Baja un peldaño si la base es menos fiable: sin dirección exacta (sin
    # Catastro), Notariado estimado, o cayó al agregado pese a pedir segmento.
    if precision != "street" or nota.get("is_estimated") or nota.get("segment_fallback"):
        conf_level = {"alta": "media", "media": "baja", "baja": "baja"}[conf_level]
    confidence = {
        "level": conf_level,
        "label": {"alta": "Alta", "media": "Media", "baja": "Baja"}[conf_level],
        "band_pct": round(band_half * 100) if band_half is not None else None,
        "reason": agreement.get("note") or "",
        # Base de comparables: "comparado con N pisos de 2ª mano en CP 28013".
        "comps_basis": {
            "n": nota.get("num_transactions"),
            "segment": nota.get("segment"),
            "level": nota.get("level"),
        } if nota.get("found") else None,
    }

    warnings = pre_warnings + list(val.get("warnings", []))
    if precision == "locality":
        warnings.append(
            "Dirección no localizada con exactitud: valoración a nivel de "
            "zona (sin año oficial del Catastro). Indica calle y número "
            "reales para afinar.")

    result: dict[str, Any] = {
        "found": True,
        "model_version": MODEL_VERSION,
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
            "interval": interval,
            "confidence": confidence,
            "location_adjustment": location_adjustment,
            "temporal_adjustment": temporal_adjustment,
            "value_eur_per_m2": value_per_m2,
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
                "segment": nota.get("segment"),
                "segment_fallback": nota.get("segment_fallback"),
                "avg_surface_m2": nota.get("avg_surface_m2") or None,
                "blend": nota.get("blend"),
            } if nota.get("found") else None,
            "mitma": {
                "price_eur_per_m2": mitma_price,
                "data_source": comps.get("data_source"),
                "data_as_of": MITMA_QUARTER,
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

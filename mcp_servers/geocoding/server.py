"""
MCP server: Geocoding (Nominatim / OpenStreetMap).

Expone una sola tool: geocode_address — convierte una dirección española en
lat/lng + barrio/distrito + display name.

Lógica portada (read-only) de decomind-partner-api/shared/geocoding.py.
Cambios respecto al original:
- httpx en lugar de requests (async-friendly, mejor para MCP)
- User-Agent identificable para el challenge
- Sin lru_cache (el servidor MCP puede vivir poco; cachear es responsabilidad del agente)
- Sin acoplamiento Azure
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

NOMINATIM_BASE_URL = os.getenv(
    "NOMINATIM_BASE_URL",
    "https://nominatim.openstreetmap.org",
).rstrip("/")
NOMINATIM_USER_AGENT = os.getenv(
    "NOMINATIM_USER_AGENT",
    "decomind-agent-challenge/0.1 (info@decomind.es)",
)
NOMINATIM_TIMEOUT_SECONDS = float(os.getenv("NOMINATIM_TIMEOUT_SECONDS", "5"))

logger = logging.getLogger("mcp.geocoding")

# Comunidades autónomas — los detectamos para EVITAR confundirlos con provincia.
# Nominatim en España suele meter la CCAA en `addr.province` o `addr.state`.
# Si vemos uno de estos nombres en el campo province, buscamos la provincia real
# en otros campos del response (state_district / county / region).
_CCAAS_NORM = {
    "andalucia", "aragon", "asturias", "principado de asturias",
    "illes balears", "islas baleares", "baleares",
    "canarias", "cantabria",
    "castilla y leon", "castilla-la mancha", "castilla la mancha",
    "cataluna", "catalunya", "cataluña",
    "comunitat valenciana", "comunidad valenciana",
    "extremadura", "galicia",
    "comunidad de madrid", "madrid",
    "region de murcia", "murcia",
    "comunidad foral de navarra", "navarra",
    "pais vasco", "euskadi",
    "la rioja", "ceuta", "melilla",
}


def _strip_diacritics(s: str) -> str:
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    ).lower().strip()


def _pick_real_province(addr: dict) -> str | None:
    """De los múltiples campos admin de Nominatim, devuelve la PROVINCIA política
    (no la CCAA). Estrategia:
      1. Intenta addr.province. Si no es una CCAA conocida, vale.
      2. Si addr.province es CCAA o falta, prueba state_district, county, region.
      3. Si todos fallan, devuelve lo que haya en addr.state (incluso si es CCAA).
    """
    candidates_primary = [addr.get("province"), addr.get("state_district"),
                          addr.get("county"), addr.get("region")]
    for c in candidates_primary:
        if c and _strip_diacritics(c) not in _CCAAS_NORM:
            return c
    # nada limpio → devolvemos lo más informativo aunque sea CCAA
    return addr.get("province") or addr.get("state")

def _municipality(addr: dict) -> str | None:
    return (addr.get("city") or addr.get("town") or addr.get("village")
            or addr.get("municipality") or addr.get("hamlet"))


def _pick_hit(data: list[dict], locality: str) -> dict:
    """El primer resultado que cae DENTRO del municipio pedido. Si ninguno
    (nombre bilingüe, pedanía, sin localidad), el primero, como antes."""
    want = {_strip_diacritics(x) for x in (locality or "").split("/") if x.strip()}
    for h in data:
        if _strip_diacritics(_municipality(h.get("address") or {}) or "") in want:
            return h
    return data[0]


mcp = FastMCP("geocoding")


@mcp.tool()
def geocode_address(
    address: str,
    locality: str = "",
    province: str = "",
    postal_code: str = "",
) -> dict[str, Any]:
    """Geocodifica una dirección española vía Nominatim (OpenStreetMap).

    Args:
        address: Calle y número. Ej: "Calle Mayor 5".
        locality: Ciudad o pueblo. Ej: "Madrid".
        province: Provincia. Ej: "Madrid".
        postal_code: Código postal. Ej: "28013".

    Returns:
        Dict con: lat, lon, neighbourhood, suburb, city_district, road,
        display_name. Si no se encuentra, devuelve {"found": False, "reason": "..."}.
    """
    if not address or not address.strip():
        return {"found": False, "reason": "empty_address"}

    # Sin repetir partes: "Oliva, Oliva, España" (zona = localidad) hacía que
    # Nominatim devolviera el Parc Natural de la Marjal Pego-Oliva, en Pego
    # (Alicante), y se valoraba con el Notariado y el MIVAU de otro pueblo.
    query_parts: list[str] = []
    for part in (address, postal_code, locality, province, "España"):
        part = (part or "").strip()
        if part and _strip_diacritics(part) not in {_strip_diacritics(p) for p in query_parts}:
            query_parts.append(part)
    query = ", ".join(query_parts)

    try:
        with httpx.Client(timeout=NOMINATIM_TIMEOUT_SECONDS) as client:
            resp = client.get(
                f"{NOMINATIM_BASE_URL}/search",
                params={
                    "q": query,
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "limit": 5,
                    "countrycodes": "es",
                    "accept-language": "es",
                },
                headers={"User-Agent": NOMINATIM_USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Nominatim failed for '%s': %s", query, exc)
        return {"found": False, "reason": f"network_error: {exc}"}

    if not data:
        return {"found": False, "reason": "no_results", "query": query}

    hit = _pick_hit(data, locality)
    addr = hit.get("address") or {}
    return {
        "found": True,
        "lat": hit.get("lat"),
        "lon": hit.get("lon"),
        # Administrativos (los que importan para lookups MITMA/curado)
        "municipality": _municipality(addr),
        "province": _pick_real_province(addr),
        "autonomous_community": addr.get("state"),  # CCAA (informativo)
        "postcode": addr.get("postcode"),
        "country": addr.get("country"),
        # Granularidad fina dentro del municipio
        "city_district": addr.get("city_district") or addr.get("district"),
        "suburb": addr.get("suburb"),
        "neighbourhood": addr.get("neighbourhood") or addr.get("quarter"),
        "road": addr.get("road"),
        # Sin número = Nominatim devolvió el CENTRO de la calle (OSM no tiene el portal).
        "house_number": addr.get("house_number"),
        "display_name": hit.get("display_name"),
    }


def _cartociudad_candidates(address: str, locality: str) -> list[dict]:
    """Candidatos de CartoCiudad (IGN) para «calle número, localidad». [] si falla."""
    try:
        resp = httpx.get(
            "https://www.cartociudad.es/geocoder/api/geocoder/candidates",
            params={"q": f"{address}, {locality}", "limit": 10},
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=NOMINATIM_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json() if resp.text.strip() else []
    except Exception as exc:
        logger.warning("CartoCiudad failed for '%s': %s", address, exc)
        return []
    return data if isinstance(data, list) else []


def _in_place(c: dict, locality: str, postal_code: str) -> bool:
    """¿El candidato es del municipio pedido (nombre bilingüe «A/B» vale) o de su CP?
    Su `find` devuelve a veces otra provincia (Mont-roig del Camp por Bellreguard)."""
    if postal_code and str(c.get("postalCode") or "") == postal_code.strip():
        return True
    want = {_strip_diacritics(x) for x in (locality or "").split("/") if x.strip()}
    have = {_strip_diacritics(x) for x in str(c.get("muni") or "").split("/") if x.strip()}
    return bool(want & have)


def cartociudad_street(address: str, locality: str, postal_code: str = "") -> dict[str, Any] | None:
    """La calle según CartoCiudad cuando Nominatim no la encuentra: su callejero
    oficial entiende la calle en castellano aunque OSM la tenga en valenciano o
    catalán («Calle Mayor 3, Oliva» → Carrer Major; «Calle Formentera,
    Bellreguard» → Carrer de Formentera). Solo un portal o calle del municipio
    pedido o de su CP. Misma forma que geocode_address (house_number solo si es
    ESE portal). None si no."""
    m = re.search(r"(\d{1,4})\s*[a-zA-Z]?\s*$", (address or "").strip())
    number = int(m.group(1)) if m else None
    for c in _cartociudad_candidates(address, locality):
        if c.get("type") not in ("portal", "callejero") or not (c.get("lat") and c.get("lng")):
            continue
        if not _in_place(c, locality, postal_code):
            continue
        parts = [p.strip() for p in str(c.get("muni") or "").split("/") if p.strip()]
        muni = next((p for p in parts if _strip_diacritics(p) in
                     {_strip_diacritics(x) for x in (locality or "").split("/")}), parts[0] if parts else locality)
        same_portal = c.get("type") == "portal" and number is not None and c.get("portalNumber") == number
        return {
            "found": True, "lat": str(c["lat"]), "lon": str(c["lng"]),
            "municipality": muni, "province": None,  # el motor usa la provincia indicada
            "postcode": c.get("postalCode"), "road": c.get("address"),
            "house_number": str(number) if same_portal else None,
            "display_name": f"{c.get('address')}, {c.get('muni')}", "source": "cartociudad",
        }
    return None


def cartociudad_portal(address: str, locality: str, number: int) -> dict[str, Any] | None:
    """Coordenadas del portal `number` según CartoCiudad (IGN), que sí tiene
    portales donde OSM no. Solo si CartoCiudad devuelve ESE número del municipio
    pedido: su `find` responde con el portal de número más cercano (p.ej. pides
    el 60 y da el 61, en la otra acera) o de otro municipio, que no sirven para
    saber qué edificio es. None si no."""
    for c in _cartociudad_candidates(address, locality):
        if c.get("type") == "portal" and c.get("portalNumber") == number and _in_place(c, locality, ""):
            return {"lat": c.get("lat"), "lon": c.get("lng"),
                    "cadastral_reference": c.get("refCatastral")}
    return None


if __name__ == "__main__":
    from mcp_servers._runtime import run_server
    run_server(mcp)

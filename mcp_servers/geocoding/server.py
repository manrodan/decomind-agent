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

    query_parts = [address.strip()]
    if postal_code:
        query_parts.append(postal_code.strip())
    if locality:
        query_parts.append(locality.strip())
    if province and province != locality:
        query_parts.append(province.strip())
    query_parts.append("España")
    query = ", ".join(p for p in query_parts if p)

    try:
        with httpx.Client(timeout=NOMINATIM_TIMEOUT_SECONDS) as client:
            resp = client.get(
                f"{NOMINATIM_BASE_URL}/search",
                params={
                    "q": query,
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "limit": 1,
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

    hit = data[0]
    addr = hit.get("address") or {}
    return {
        "found": True,
        "lat": hit.get("lat"),
        "lon": hit.get("lon"),
        # Administrativos (los que importan para lookups MITMA/curado)
        "municipality": (
            addr.get("city") or addr.get("town") or addr.get("village")
            or addr.get("municipality") or addr.get("hamlet")
        ),
        "province": _pick_real_province(addr),
        "autonomous_community": addr.get("state"),  # CCAA (informativo)
        "postcode": addr.get("postcode"),
        "country": addr.get("country"),
        # Granularidad fina dentro del municipio
        "city_district": addr.get("city_district") or addr.get("district"),
        "suburb": addr.get("suburb"),
        "neighbourhood": addr.get("neighbourhood") or addr.get("quarter"),
        "road": addr.get("road"),
        "display_name": hit.get("display_name"),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")

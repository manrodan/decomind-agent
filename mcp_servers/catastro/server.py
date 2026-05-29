"""
MCP server: Catastro — datos físicos OFICIALES del inmueble.

Usa los servicios web LIBRES de la Sede Electrónica del Catastro (gratis, sin
autenticación, datos no protegidos). Devuelve superficie, año de construcción
y uso reales — eliminando el input manual propenso a error.

Datos NO protegidos (libres): referencia catastral, superficie, año, uso.
Datos protegidos (NO usamos): valor catastral, titularidad.

Pipeline interno de `catastro_lookup`:
  1. Consulta_RCCOOR_Distancia(lat, lon) → parcela catastral más cercana
     (robusto: las coords de geocoding caen en la calle, no sobre la parcela).
  2. Consulta_DNPRC(rc_parcela) → lista de inmuebles del edificio.
  3. Consulta_DNPRC(rc_inmueble_20) → detalle: año, uso, superficie.

Endpoints (HTTP, no HTTPS — el Catastro va mejor en HTTP):
  http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/...
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

BASE = "http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC"
HEADERS = {"User-Agent": "decomind-agent-challenge/0.1 (info@decomind.es)"}
TIMEOUT = 12.0

logger = logging.getLogger("mcp.catastro")
mcp = FastMCP("catastro")


# ── helpers XML (ignoran namespace con wildcard {*}) ───────────────────────

def _text(node: ET.Element | None, path: str) -> str | None:
    if node is None:
        return None
    found = node.find(path)
    return found.text.strip() if found is not None and found.text else None


def _get_xml(endpoint: str, params: dict) -> ET.Element | None:
    try:
        with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as c:
            r = c.get(f"{BASE}/{endpoint}", params=params)
            r.raise_for_status()
            return ET.fromstring(r.text)
    except Exception as exc:
        logger.warning("Catastro %s failed: %s", endpoint, exc)
        return None


def _has_error(root: ET.Element | None) -> str | None:
    """Devuelve la descripción de error del Catastro si la hay."""
    if root is None:
        return "network_error"
    err = root.find(".//{*}lerr/{*}err/{*}des")
    if err is not None and err.text:
        return err.text.strip()
    return None


def _nearest_parcel(lat: float, lon: float) -> dict[str, Any] | None:
    """Consulta_RCCOOR_Distancia → parcela más cercana (RC 14 + dirección)."""
    root = _get_xml(
        "OVCCoordenadas.asmx/Consulta_RCCOOR_Distancia",
        {"SRS": "EPSG:4326", "Coordenada_X": lon, "Coordenada_Y": lat},
    )
    if _has_error(root):
        return None
    # primer <pcd> = el más cercano (lista ordenada por distancia)
    pcd = root.find(".//{*}pcd") if root is not None else None
    if pcd is None:
        return None
    pc1 = _text(pcd, "{*}pc/{*}pc1")
    pc2 = _text(pcd, "{*}pc/{*}pc2")
    if not (pc1 and pc2):
        return None
    return {
        "cadastral_ref": pc1 + pc2,         # RC parcela (14)
        "address": _text(pcd, "{*}ldt"),    # "CL MAYOR 5 MADRID (MADRID)"
        "distance_m": float(_text(pcd, "{*}dis") or 0),
    }


def _building_units(rc_parcel: str) -> list[str]:
    """Consulta_DNPRC(RC parcela) → lista de RC completas (20) de inmuebles."""
    root = _get_xml(
        "OVCCallejero.asmx/Consulta_DNPRC",
        {"Provincia": "", "Municipio": "", "RC": rc_parcel},
    )
    if root is None or _has_error(root):
        return []
    units: list[str] = []
    for rc in root.findall(".//{*}lrcdnp/{*}rcdnp/{*}rc"):
        pc1 = _text(rc, "{*}pc1") or ""
        pc2 = _text(rc, "{*}pc2") or ""
        car = _text(rc, "{*}car") or ""
        cc1 = _text(rc, "{*}cc1") or ""
        cc2 = _text(rc, "{*}cc2") or ""
        full = pc1 + pc2 + car + cc1 + cc2
        if len(full) >= 20:
            units.append(full)
    return units


def _unit_detail(rc20: str) -> dict[str, Any] | None:
    """Consulta_DNPRC(RC 20) → {use, surface_m2, year_built, address}."""
    root = _get_xml(
        "OVCCallejero.asmx/Consulta_DNPRC",
        {"Provincia": "", "Municipio": "", "RC": rc20},
    )
    if root is None or _has_error(root):
        return None
    bi = root.find(".//{*}bico/{*}bi")
    if bi is None:
        return None
    debi = bi.find("{*}debi")
    use = _text(debi, "{*}luso") if debi is not None else None
    sfc = _text(debi, "{*}sfc") if debi is not None else None
    ant = _text(debi, "{*}ant") if debi is not None else None
    return {
        "use": use,
        "surface_m2": int(sfc) if sfc and sfc.isdigit() else None,
        "year_built": int(ant) if ant and ant.isdigit() else None,
        "address_full": _text(bi, "{*}ldt"),
    }


# ── tools ──────────────────────────────────────────────────────────────────

@mcp.tool()
def catastro_lookup(lat: float, lon: float) -> dict[str, Any]:
    """Obtiene datos OFICIALES del Catastro de un inmueble desde coordenadas.

    Encadena 3 servicios web libres del Catastro español para devolver el año
    de construcción, el uso y la superficie de referencia del edificio en esas
    coordenadas. Pensado para alimentarse de la salida de `geocode_address`.

    Args:
        lat: Latitud (EPSG:4326), p.ej. 40.4163773.
        lon: Longitud (EPSG:4326), p.ej. -3.705515.

    Returns:
        {
          "found": bool,
          "cadastral_reference": str,    # RC de la parcela (14 chars)
          "address": str,                # dirección oficial confirmada
          "distance_m": float,           # distancia coords → parcela
          "year_built": int | None,      # año de construcción del edificio
          "primary_use": str | None,     # "Residencial" | "Comercial" | ...
          "surface_m2_reference": int | None,  # superficie del inmueble muestreado
          "units_count": int,            # nº de inmuebles en el edificio
          "note": str,                   # aclaración de procedencia / limitación
        }
        Si no se encuentra: {"found": False, "reason": "..."}.
    """
    parcel = _nearest_parcel(lat, lon)
    if not parcel:
        return {"found": False, "reason": "no_parcel_for_coordinates"}

    units = _building_units(parcel["cadastral_ref"])

    # Itera por los inmuebles del edificio hasta encontrar uno con año (y
    # preferiblemente residencial). El primer inmueble puede ser un local sin
    # año; el año es del edificio, así que cualquiera con dato sirve.
    detail = None
    first_with_year = None
    for rc20 in units[:8]:
        d = _unit_detail(rc20)
        if not d:
            continue
        if d.get("year_built"):
            if first_with_year is None:
                first_with_year = d
            use = (d.get("use") or "").lower()
            if "residencial" in use or "vivienda" in use:
                detail = d
                break
    if detail is None:
        detail = first_with_year or (_unit_detail(units[0]) if units else None)

    result: dict[str, Any] = {
        "found": True,
        "cadastral_reference": parcel["cadastral_ref"],
        "address": parcel["address"],
        "distance_m": parcel["distance_m"],
        "units_count": len(units),
        "year_built": detail["year_built"] if detail else None,
        "primary_use": detail["use"] if detail else None,
        "surface_m2_reference": detail["surface_m2"] if detail else None,
        "note": (
            "Año y uso son del edificio (Catastro oficial, datos no protegidos). "
            "La superficie de referencia corresponde a un inmueble muestreado del "
            "edificio; la superficie del piso concreto puede diferir."
        ),
    }
    return result


@mcp.tool()
def catastro_unit_detail(cadastral_reference: str) -> dict[str, Any]:
    """Detalle de un inmueble concreto por su referencia catastral completa (20).

    Args:
        cadastral_reference: RC completa de 20 caracteres (parcela + cargo +
            control), p.ej. "0244802VK4704C0001AX".

    Returns:
        {found, use, surface_m2, year_built, address_full} o {found: False}.
    """
    detail = _unit_detail(cadastral_reference.strip().upper())
    if not detail:
        return {"found": False, "reason": "not_found_or_invalid_rc"}
    return {"found": True, **detail}


if __name__ == "__main__":
    from mcp_servers._runtime import run_server
    run_server(mcp)

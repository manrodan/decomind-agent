"""
MCP server: Zona de Valor del Catastro — ajuste FINO de ubicación intra-CP.

Fuente: WMS público de Ponencias del Catastro (ovc.catastro.meh.es), capa
"ZONA VALOR". Por coordenada devuelve la zona de valor homogénea del punto
(calle/manzana) y su módulo €/m² (repercusión de suelo) de la ponencia municipal.

NO es valor de mercado (es valor catastral): se usa SOLO como GRADIENTE relativo
—¿esta calle está por encima/debajo de su entorno inmediato?— para afinar la
ubicación sobre el precio REAL del Notariado, que solo baja a nivel código postal.
El anillo (no el municipio) como baseline evita doble-contar la ubicación que el
Notariado ya captura por CP. Donde no hay cobertura (mucha España; País Vasco y
Navarra tienen catastro foral propio), degrada a gradiente 1.0 (no-op).

Contrato verificado en vivo (2026-06-19) — capa "ZONA VALOR" con datos en Madrid,
Barcelona, Valencia, Zaragoza, Murcia; sin datos en Sevilla, Málaga, forales, etc.
"""
from __future__ import annotations

import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

WMS = "https://ovc.catastro.meh.es/Cartografia/WMS/PonenciasWMS.aspx"
PONENCIA = "https://ovc.catastro.meh.es/Cartografia/WMS/ponencia.aspx"
HEADERS = {"User-Agent": "decomind-agent-challenge/0.1 (info@decomind.es)"}
TIMEOUT = 15.0

# Gradiente acotado a ±12%: es un AJUSTE FINO, nunca un ancla. El índice catastral
# no mapea 1:1 al mercado, así que se topa para no sobre-aplicar.
_BOUND = 0.12

logger = logging.getLogger("mcp.zona_valor")
mcp = FastMCP("zona_valor")

# Caché de proceso: ponencia por (del, mun) -> {codigo_zona: €/m²}. Dato anual.
# ponytail: dict en memoria del proceso; subir a TTL/persistente solo si escala.
_PONENCIA_CACHE: dict[tuple[str, str], dict[str, float]] = {}


def _merc(lon: float, lat: float) -> tuple[float, float]:
    """lon/lat (EPSG:4326) -> EPSG:3857 (mercator esférico), que es el SRS del WMS."""
    R = 6378137.0
    return (math.radians(lon) * R,
            math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * R)


def _ponencia_values(delg: str, mun: str) -> dict[str, float]:
    """{codigo_zona: €/m²} de la ponencia del municipio (cacheado). {} si falla."""
    key = (delg, mun)
    if key in _PONENCIA_CACHE:
        return _PONENCIA_CACHE[key]
    out: dict[str, float] = {}
    try:
        with httpx.Client(timeout=40, headers=HEADERS, follow_redirects=True) as c:
            r = c.get(PONENCIA, params={"del": delg, "mun": mun})
            r.raise_for_status()
            text = r.text
        for code, val in re.findall(
            r'prod_cat2">([^<]+)</td><td class="tddescrip_centrado">\s*([\d.]+)', text
        ):
            try:
                out[code.strip()] = float(val)
            except ValueError:
                continue
    except Exception as exc:
        logger.warning("ponencia(%s,%s) failed: %s", delg, mun, exc)
    _PONENCIA_CACHE[key] = out
    return out


def zona_valor_lookup(lat: float, lon: float) -> dict[str, Any]:
    """Zona de valor + €/m² catastral del punto. {found: False} si no hay cobertura."""
    x, y = _merc(lon, lat)
    d = 35.0  # bbox ±35 m: el píxel central (50,50) cae sobre el punto
    params = {
        "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetFeatureInfo",
        "LAYERS": "ZONA VALOR", "QUERY_LAYERS": "ZONA VALOR", "SRS": "EPSG:3857",
        "BBOX": f"{x - d},{y - d},{x + d},{y + d}", "WIDTH": "101", "HEIGHT": "101",
        "X": "50", "Y": "50", "INFO_FORMAT": "text/html", "FEATURE_COUNT": "1",
    }
    try:
        with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as c:
            r = c.get(WMS, params=params)
            r.raise_for_status()
            text = r.text
    except Exception as exc:
        logger.warning("zona_valor GFI failed: %s", exc)
        return {"found": False}
    return _parse_gfi(text)


def _parse_gfi(text: str) -> dict[str, Any]:
    """Extrae código de zona + €/m² del HTML del GetFeatureInfo (sin red: testeable)."""
    cells = [re.sub(r"<[^>]+>", "", m).strip()
             for m in re.findall(r"<td[^>]*>(.*?)</td>", text, re.S)]
    cells = [c for c in cells if c]
    code = next((c for c in cells if re.fullmatch(r"[A-Z]?\d{1,4}[A-Z]?", c)), None)
    dm = re.findall(r"ponencia\.aspx\?del=(\d+)&mun=(\d+)", text)
    if not code or not dm or dm[0][1] == "0":
        return {"found": False}
    delg, mun = dm[0]
    value = _ponencia_values(delg, mun).get(code)
    if not value:
        return {"found": False}
    return {"found": True, "code": code, "value": value, "del": delg, "mun": mun}


def _value_at(lat: float, lon: float) -> float | None:
    z = zona_valor_lookup(lat, lon)
    return z["value"] if z.get("found") else None


def _clamp_gradient(subject: float, mean: float, bound: float = _BOUND) -> float:
    """Gradiente sujeto/entorno acotado a [1-bound, 1+bound]. Función pura (testeable)."""
    if not mean or mean <= 0:
        return 1.0
    return max(1 - bound, min(1 + bound, subject / mean))


@mcp.tool()
def zona_valor_gradient(lat: float, lon: float, radius_m: float = 300.0,
                        n: int = 8) -> dict[str, Any]:
    """Gradiente de ubicación: €/m² de la zona del punto ÷ media de su entorno
    (anillo de radius_m), acotado a ±12% (ajuste fino).

    Devuelve {found, gradient, raw_gradient, subject, neighborhood_mean, zone_code, n}.
    {found: False, gradient: 1.0} si el punto no tiene cobertura de zona de valor
    → el motor lo trata como no-op (no toca el precio del Notariado).
    """
    subj = zona_valor_lookup(lat, lon)
    if not subj.get("found"):
        return {"found": False, "gradient": 1.0}

    pts: list[tuple[float, float]] = []
    coslat = math.cos(math.radians(lat)) or 1e-6
    for i in range(max(1, n)):
        a = 2 * math.pi * i / max(1, n)
        dlat = radius_m * math.sin(a) / 110540.0
        dlon = radius_m * math.cos(a) / (111320.0 * coslat)
        pts.append((lat + dlat, lon + dlon))

    # Muestreo del anillo EN PARALELO (si no, ~9 GFI secuenciales = ~2-3 s).
    with ThreadPoolExecutor(max_workers=min(8, len(pts))) as ex:
        ring = [v for v in ex.map(lambda p: _value_at(*p), pts) if v]

    vals = [subj["value"]] + ring
    mean = sum(vals) / len(vals)
    raw = subj["value"] / mean if mean > 0 else 1.0
    return {
        "found": True,
        "gradient": round(_clamp_gradient(subj["value"], mean), 4),
        "raw_gradient": round(raw, 4),
        "subject": subj["value"],
        "neighborhood_mean": round(mean, 1),
        "zone_code": subj["code"],
        "n": len(vals),
    }


if __name__ == "__main__":
    from mcp_servers._runtime import run_server
    run_server(mcp)

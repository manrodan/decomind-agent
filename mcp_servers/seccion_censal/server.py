"""
MCP server: Sección censal — señal de MERCADO ACTUAL para la micro-ubicación.

Complementa (y corrige) el gradiente de zona de valor del Catastro: las
ponencias catastrales pueden tener décadas y clasificar mal calles que han
mejorado/empeorado desde que se redactaron. Aquí usamos dos señales VIVAS,
oficiales y por sección censal (~1.000-2.500 habitantes, más fino que el CP):

  - Alquiler €/m²/mes (SERPAVI, MITMA/MIVAU): lo que el mercado paga HOY por
    vivir en esa sección.
  - Renta neta media por hogar (Atlas de Renta del INE): el poder adquisitivo
    del barrio.

Gradiente = media geométrica de (alquiler_sección/alquiler_municipio) y
(renta_sección/renta_municipio), amortiguada (los ratios de alquiler y renta
comprimen respecto a los de precio de venta) y acotada. Sin datos → no-op.

Resolución coordenada → sección: OGC API Features del INE (GeoServer público,
JSON, sin key), colección Secciones_<año>, consulta por bbox mínimo.
Dataset local: data/seccion_signal.json (lo construye
scripts/build_seccion_signal.py a partir de SERPAVI + ineAtlas/ADRH).
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

INE_FEATURES = ("https://www.ine.es/geoserver/ogc/features/v1/collections/"
                "WMS_INE_SECCIONES_G01:Secciones_2025/items")
HEADERS = {"User-Agent": "decomind-agent-challenge/0.1 (info@decomind.es)"}
TIMEOUT = 20.0

# El ratio de alquiler/renta comprime frente al de precio de venta (yields más
# bajos en zonas caras) → elasticidad <1. ponytail: 0.7 punto de partida;
# calibrar con cierres reales junto con el resto de elasticidades.
_ELASTICITY = 0.7
_BOUND = 0.25

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DATA_PATH = _DATA_DIR / "seccion_signal.json"
_STOCK_AGE_PATH = _DATA_DIR / "stock_age.json"

logger = logging.getLogger("mcp.seccion_censal")
mcp = FastMCP("seccion_censal")

_data_cache: dict[str, Any] | None = None
_stock_cache: dict[str, Any] | None = None


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("%s no disponible: %s", path.name, exc)
        return {}


def _load_data() -> dict[str, Any]:
    global _data_cache
    if _data_cache is None:
        _data_cache = _load_json(_DATA_PATH)
    return _data_cache


def stock_age_year(cusec: str | None, cumun: str | None) -> int | None:
    """Año mediano de construcción del parque de la sección (Censo/INE), con
    fallback al municipio. None sin dato → antigüedad absoluta en el hedónico."""
    global _stock_cache
    if _stock_cache is None:
        _stock_cache = _load_json(_STOCK_AGE_PATH)
    y = None
    if cusec:
        y = (_stock_cache.get("secciones") or {}).get(cusec)
    if not y and cumun:
        y = (_stock_cache.get("municipios") or {}).get(cumun)
    return int(y) if y else None


def seccion_lookup(lat: float, lon: float) -> dict[str, Any]:
    """Sección censal (CUSEC) del punto vía OGC API del INE. {found: False} si falla."""
    d = 0.00008  # ~8 m: bbox mínimo alrededor del punto
    params = {
        "f": "application/json",
        "bbox": f"{lon - d},{lat - d},{lon + d},{lat + d}",
        "limit": 5,
    }
    try:
        with httpx.Client(timeout=TIMEOUT, headers=HEADERS) as c:
            r = c.get(INE_FEATURES, params=params)
            r.raise_for_status()
            feats = r.json().get("features") or []
    except Exception as exc:
        logger.warning("seccion_lookup failed: %s", exc)
        return {"found": False}
    secciones = [f.get("properties", {}) for f in feats
                 if f.get("properties", {}).get("TIPO") == "SECCIONADO"]
    if not secciones:
        return {"found": False}
    p = secciones[0]
    return {"found": True, "cusec": p.get("CUSEC"), "cumun": p.get("CUMUN"),
            "municipality": p.get("NMUN")}


def _signal_from_data(data: dict, cusec: str, cumun: str) -> dict[str, Any] | None:
    """Ratios sección/municipio de alquiler y renta. Función pura (testeable).

    data = {"secciones": {CUSEC: [alq, renta]}, "municipios": {CUMUN: [alq, renta]}}
    Devuelve {"ratios": [..], "alq": .., "renta": .., "alq_muni": .., "renta_muni": ..}
    o None si no hay ningún ratio calculable.
    """
    sec = (data.get("secciones") or {}).get(cusec)
    mun = (data.get("municipios") or {}).get(cumun)
    if not sec or not mun:
        return None
    ratios = []
    out: dict[str, Any] = {}
    for i, key in enumerate(("alq", "renta")):
        s, m = sec[i] if len(sec) > i else None, mun[i] if len(mun) > i else None
        if s and m and s > 0 and m > 0:
            ratios.append(s / m)
            out[key] = s
            out[f"{key}_muni"] = m
    if not ratios:
        return None
    out["ratios"] = ratios
    return out


def _gradient_from_ratios(ratios: list[float], bound: float = _BOUND,
                          elasticity: float = _ELASTICITY) -> float:
    """Media geométrica de los ratios, amortiguada y acotada. Función pura."""
    if not ratios:
        return 1.0
    gmean = math.exp(sum(math.log(r) for r in ratios) / len(ratios))
    return max(1 - bound, min(1 + bound, gmean ** elasticity))


@mcp.tool()
def seccion_signal_gradient(lat: float, lon: float, cusec: str = "",
                            cumun: str = "") -> dict[str, Any]:
    """Gradiente de micro-ubicación por señal de mercado actual: alquiler
    (SERPAVI) y renta por hogar (INE) de la sección censal vs su municipio,
    amortiguado (**0.7) y acotado a ±25%.

    Con `cusec`/`cumun` ya resueltos (el engine hace el lookup una vez y lo
    reutiliza) se ahorra la llamada al INE.

    Devuelve {found, gradient, cusec, alq, alq_muni, renta, renta_muni}.
    {found: False, gradient: 1.0} sin cobertura → no-op para el motor.
    """
    sec = ({"found": True, "cusec": cusec, "cumun": cumun}
           if cusec and cumun else seccion_lookup(lat, lon))
    if not sec.get("found"):
        return {"found": False, "gradient": 1.0}
    sig = _signal_from_data(_load_data(), sec["cusec"], sec["cumun"])
    if not sig:
        return {"found": False, "gradient": 1.0, "cusec": sec["cusec"]}
    g = _gradient_from_ratios(sig.pop("ratios"))
    return {"found": True, "gradient": round(g, 4), "cusec": sec["cusec"], **{
        k: (round(v, 2) if isinstance(v, float) else v) for k, v in sig.items()
    }}


if __name__ == "__main__":
    from mcp_servers._runtime import run_server
    run_server(mcp)

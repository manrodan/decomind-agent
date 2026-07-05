"""
MCP server: Zona de Valor del Catastro — ajuste de ubicación intra-CP.

Fuente: WMS público de Ponencias del Catastro (ovc.catastro.meh.es), capa
"ZONA VALOR". Por coordenada devuelve la zona de valor homogénea del punto
(calle/manzana) y su módulo €/m² (repercusión de suelo) de la ponencia municipal.

NO es valor de mercado (es valor catastral): se usa como GRADIENTE relativo
—¿la zona del inmueble está por encima/debajo del ámbito cuyo precio da el
Notariado?— para afinar la ubicación sobre el €/m² del Notariado, que no baja
del código postal. El baseline es la MEDIANA de las zonas de la ponencia
municipal (proxy del ámbito del Notariado: en municipios de un solo CP —
Benicàssim — es exacto; en ciudades multi-CP puede solapar parte de la
ubicación que el CP ya captura, y por eso el ratio catastral se AMORTIGUA con
una elasticidad <1 antes de aplicarse). El anillo local de 300 m que se usaba
antes comparaba la calle con su propio barrio → gradiente ~1.0 siempre, y
dejaba pasar diferencias reales de 2-3x intra-CP (Voramar vs centro en
Benicàssim; Centro vs Universidad en Castellón).

Donde no hay cobertura (País Vasco y Navarra con catastro foral; municipios sin
ponencia en el WMS), degrada a gradiente 1.0 (no-op). En primera línea de costa
el píxel exacto cae a veces en playa/mar sin zona → muestreo de respaldo en
anillos de 80/200 m alrededor del punto.

Contrato verificado en vivo (2026-06-19; ampliado 2026-07-05 con Benicàssim
del=12 mun=028, 42 zonas 28→1700 €/m², y Castellón capital).
"""
from __future__ import annotations

import logging
import math
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

WMS = "https://ovc.catastro.meh.es/Cartografia/WMS/PonenciasWMS.aspx"
PONENCIA = "https://ovc.catastro.meh.es/Cartografia/WMS/ponencia.aspx"
HEADERS = {"User-Agent": "decomind-agent-challenge/0.1 (info@decomind.es)"}
TIMEOUT = 15.0

# El índice catastral no mapea 1:1 al mercado: el ratio zona/ámbito se amortigua
# con `ratio ** _ELASTICITY` y se acota a ±_BOUND. ponytail: elasticidad 0.5 es
# el punto de partida sin calibrar; el upgrade es ajustarla con precios de cierre
# reales de los agentes (bucle de backtesting del roadmap).
_BOUND = 0.30
_ELASTICITY = 0.5
# Radios del muestreo de respaldo cuando el punto exacto no tiene zona (playa,
# borde de polígono): 8 puntos por anillo, se queda con la zona más frecuente.
# 400 m cubre paseos marítimos anchos (1ª línea = donde más valor se pierde).
_FALLBACK_RADII_M = (80.0, 200.0, 400.0)

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


def _ring_points(lat: float, lon: float, radius_m: float, n: int = 8) -> list[tuple[float, float]]:
    coslat = math.cos(math.radians(lat)) or 1e-6
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        pts.append((lat + radius_m * math.sin(a) / 110540.0,
                    lon + radius_m * math.cos(a) / (111320.0 * coslat)))
    return pts


def _pick_fallback_zone(hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Elige la zona del muestreo de respaldo: preferencia por zonas R
    (residencial — lo que se está valorando es vivienda; las U/PU del borde
    suelen ser equipamiento/urbanizable), luego la más frecuente y, en empate,
    la de mayor valor (determinista). Verificado en el hotel Voramar: el anillo
    ve U25 y R17 → debe ganar R17 (la 1ª línea real). Función pura (testeable)."""
    res = [h for h in hits if h["code"].startswith("R")]
    pool = res if res else hits
    codes = [h["code"] for h in pool]
    best = max(set(codes), key=lambda c: (codes.count(c), next(
        h["value"] for h in pool if h["code"] == c)))
    return next(h for h in pool if h["code"] == best)


def _lookup_with_fallback(lat: float, lon: float) -> dict[str, Any]:
    """Zona del punto; si el píxel exacto no tiene (playa/borde), muestrea anillos
    de respaldo crecientes y elige con `_pick_fallback_zone`."""
    subj = zona_valor_lookup(lat, lon)
    if subj.get("found"):
        return subj
    for radius in _FALLBACK_RADII_M:
        pts = _ring_points(lat, lon, radius)
        with ThreadPoolExecutor(max_workers=len(pts)) as ex:
            hits = [z for z in ex.map(lambda p: zona_valor_lookup(*p), pts) if z.get("found")]
        if hits:
            z = _pick_fallback_zone(hits)
            z["fallback_m"] = radius
            return z
    return {"found": False}


def _ambito_median(values: dict[str, float]) -> float | None:
    """Mediana de las zonas RESIDENCIALES (código R*) de la ponencia municipal
    = baseline del gradiente.

    Solo R: las U/PU (25-450 €/m²) y las PR (que en Castellón capital son bajas
    pero en Benicàssim duplican a las R) contaminan la mediana en un sentido u
    otro según el municipio. Verificado 2026-07-05: con R-only la mediana de
    Benicàssim es 835 (la zona del centro = gradiente neutro, como debe) y la de
    Castellón 537 (centro +25%, universidad al suelo). Mediana (no media) por
    robustez a outliers. Sin zonas R → todas las zonas como respaldo.
    """
    if not values:
        return None
    res = [v for c, v in values.items() if c.startswith("R")]
    return statistics.median(res if res else list(values.values()))


def _clamp_gradient(subject: float, baseline: float, bound: float = _BOUND,
                    elasticity: float = _ELASTICITY) -> float:
    """Gradiente de MERCADO desde el ratio catastral: (subject/baseline)**elasticity,
    acotado a [1-bound, 1+bound]. Función pura (testeable)."""
    if not baseline or baseline <= 0 or not subject or subject <= 0:
        return 1.0
    return max(1 - bound, min(1 + bound, (subject / baseline) ** elasticity))


@mcp.tool()
def zona_valor_gradient(lat: float, lon: float) -> dict[str, Any]:
    """Gradiente de ubicación intra-CP: €/m² catastral de la zona del inmueble ÷
    mediana de las zonas de su ponencia municipal, amortiguado (**0.5) y acotado
    a ±30%.

    Devuelve {found, gradient, raw_gradient, subject, neighborhood_mean, zone_code, n}.
    (`neighborhood_mean` conserva su nombre por compatibilidad con el engine,
    pero ahora es la mediana municipal, no la media del anillo.)
    {found: False, gradient: 1.0} si el punto no tiene cobertura de zona de valor
    → el motor lo trata como no-op (no toca el precio del Notariado).
    """
    subj = _lookup_with_fallback(lat, lon)
    if not subj.get("found"):
        return {"found": False, "gradient": 1.0}

    table = _ponencia_values(subj["del"], subj["mun"])
    baseline = _ambito_median(table)
    if not baseline:
        return {"found": False, "gradient": 1.0}

    raw = subj["value"] / baseline
    out = {
        "found": True,
        "gradient": round(_clamp_gradient(subj["value"], baseline), 4),
        "raw_gradient": round(raw, 4),
        "subject": subj["value"],
        "neighborhood_mean": round(baseline, 1),
        "zone_code": subj["code"],
        "n": len(table),
    }
    if subj.get("fallback_m"):
        out["fallback_m"] = subj["fallback_m"]
    return out


if __name__ == "__main__":
    from mcp_servers._runtime import run_server
    run_server(mcp)

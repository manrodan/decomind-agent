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
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_servers.catastro.server import catastro_get

WMS = "https://ovc.catastro.meh.es/Cartografia/WMS/PonenciasWMS.aspx"
PONENCIA = "https://ovc.catastro.meh.es/Cartografia/WMS/ponencia.aspx"
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
# Tope de tiempo del muestreo de respaldo (va en serie, ver abajo): con el
# Catastro lento (2-4 s por petición) los 24 puntos pasarían del timeout de
# 60 s de Cloud Run. Agotado el tope (o al primer corte) se decide con los
# puntos ya vistos.
_FALLBACK_BUDGET_S = 8.0

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


def _ponencia_values(delg: str, mun: str) -> dict[str, float] | None:
    """{codigo_zona: €/m²} de la ponencia del municipio (cacheado). None si la
    descarga falla — sin cachear: un corte puntual no deja al municipio sin zona
    de valor el resto de la vida de la instancia."""
    key = (delg, mun)
    if key in _PONENCIA_CACHE:
        return _PONENCIA_CACHE[key]
    out: dict[str, float] = {}
    try:
        text = catastro_get(PONENCIA, {"del": delg, "mun": mun}, timeout=40).text
        for code, val in re.findall(
            r'prod_cat2">([^<]+)</td><td class="tddescrip_centrado">\s*([\d.]+)', text
        ):
            try:
                out[code.strip()] = float(val)
            except ValueError:
                continue
    except Exception as exc:
        logger.warning("ponencia(%s,%s) failed: %s", delg, mun, exc)
        return None
    _PONENCIA_CACHE[key] = out
    return out


def zona_valor_lookup(lat: float, lon: float) -> dict[str, Any]:
    """Zona de valor + €/m² catastral del punto. {found: False} si no hay
    cobertura; además `error` si el Catastro no respondió (ya reintentado)."""
    x, y = _merc(lon, lat)
    d = 35.0  # bbox ±35 m: el píxel central (50,50) cae sobre el punto
    params = {
        "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetFeatureInfo",
        "LAYERS": "ZONA VALOR", "QUERY_LAYERS": "ZONA VALOR", "SRS": "EPSG:3857",
        "BBOX": f"{x - d},{y - d},{x + d},{y + d}", "WIDTH": "101", "HEIGHT": "101",
        "X": "50", "Y": "50", "INFO_FORMAT": "text/html", "FEATURE_COUNT": "1",
    }
    try:
        text = catastro_get(WMS, params, timeout=TIMEOUT).text
    except Exception as exc:
        logger.warning("zona_valor GFI failed: %s", exc)
        return {"found": False, "error": True}
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
    values = _ponencia_values(delg, mun)
    if values is None:
        return {"found": False, "error": True}
    value = values.get(code)
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
    de respaldo crecientes y elige con `_pick_fallback_zone`.

    En SERIE y cortando al primer error: el Catastro admite ~2 conexiones
    simultáneas por IP y el anillo en paralelo (8) perdía el 87 % de las
    peticiones (logs sep-2026). Si el Catastro no responde, el anillo no se
    lanza — es para píxeles sin zona, no para un Catastro caído."""
    subj = zona_valor_lookup(lat, lon)
    if subj.get("found") or subj.get("error"):
        return subj
    deadline = time.monotonic() + _FALLBACK_BUDGET_S
    cut = False
    for radius in _FALLBACK_RADII_M:
        hits = []
        for p in _ring_points(lat, lon, radius):
            if time.monotonic() > deadline:
                break
            z = zona_valor_lookup(*p)
            if z.get("error"):
                deadline, cut = 0.0, True  # corte (ya reintentado): no insistir
                break
            if z.get("found"):
                hits.append(z)
        if hits:
            z = _pick_fallback_zone(hits)
            z["fallback_m"] = radius
            return z
    # Con corte, «sin zona» no es «sin cobertura»: el motor lo marca como fuente caída.
    return {"found": False, "error": True} if cut else {"found": False}


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
        return {"found": False, "gradient": 1.0, **({"error": True} if subj.get("error") else {})}

    table = _ponencia_values(subj["del"], subj["mun"])
    baseline = _ambito_median(table)
    if not baseline:  # table None = la descarga de la ponencia falló
        return {"found": False, "gradient": 1.0, **({"error": True} if table is None else {})}

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


# ── Mapa de valores de referencia (Sede del Catastro) ──────────────────────
# Ámbitos territoriales homogéneos con el módulo €/m² del producto inmobiliario
# representativo, derivado de las COMPRAVENTAS ante notario (mapa del ejercicio
# N = dato de N-1; el de N+1 se publica a finales de octubre). Público, sin
# identificación; una petición devuelve TODOS los ámbitos del municipio del
# punto (polígonos WGS84, ~400 KB) → caché de proceso por municipio.
# Fuente PREFERENTE del gradiente 6a del engine (ventas firmadas, anual,
# cobertura total salvo forales); la ponencia (valor IBI) queda de respaldo
# cuando no hay ámbito, el producto de la zona es de otra clase (chalet en zona
# de pisos) o el servicio no responde. Nivel absoluto NO utilizable (producto
# tipo de 32-50 años: ~0,5 del mercado); solo el ratio zona/municipio.
# Verificado 2026-11-07: Benicàssim 26 ámbitos (pueblo 1.430-1.550 €/m², playa
# 2.500-3.430, villas hasta 5.200); evals/CATASTRO_MAPA_VALORES.md.
MAPA_VALORES = "https://www1.sedecatastro.gob.es/Cartografia/SECDameGeoJSON.aspx"
_MAPA_TIMEOUT = 10.0  # ×2 años en el peor caso; Madrid (8 MB) tarda ~3 s
_MAPA_CACHE: dict[tuple[str, str], dict[str, Any]] = {}  # (del, mun) -> {anyo, zonas, bbox}
_MAPA_MISS: dict[tuple[float, float], float] = {}  # punto redondeado (~100 m) sin ámbito -> hora
_MAPA_MISS_TTL_S = 3600.0
_MAPA_RADII_M = (80.0, 200.0, 400.0)  # respaldo SIN red: punto en playa/borde de polígono
_MAPA_BBOX_MARGEN = 0.006  # grados (~500 m): el anillo de respaldo puede salir del bbox
# Ciudades multi-CP (Madrid 678 ámbitos, Valencia 150): el Notariado por CP ya
# captura parte de la ubicación y el 17 % de los ámbitos de Madrid saturan el
# ±30 %. ponytail: tope más corto hasta tener backtest con Madrid/Valencia.
_MAPA_GRANDE = 100
_MAPA_BOUND_GRANDE = 0.15


def _clase_producto(tipologia: str | None) -> str | None:
    """Tipología del producto del ámbito → clase del motor (piso / unifamiliar)."""
    t = (tipologia or "").lower()
    return "piso" if "colectiva" in t else ("unifamiliar" if "unifamiliar" in t else None)


def _zona_de_feature(f: dict[str, Any]) -> dict[str, Any] | None:
    """Feature del GeoJSON → {cod, n, productos:[{clase, m2, tipologia}], anillos}. None sin dato."""
    p = f.get("properties") or {}
    productos = []
    n_zona = int(p.get("num_inmuebles_uso_v") or 0)
    for key in ("Ptipo1", "Ptipo2"):
        pt = p.get(key) or {}
        clase = _clase_producto(pt.get("tipologia"))
        m2 = pt.get("val_tipo_m2") or 0
        if clase and m2 > 0:
            productos.append({"clase": clase, "m2": float(m2), "tipologia": pt["tipologia"],
                              "n": int(pt.get("num_inmueble") or 0) or n_zona})
    geom = f.get("geometry") or {}
    polys = [geom["coordinates"]] if geom.get("type") == "Polygon" else geom.get("coordinates") or []
    poligonos = [(poly[0], poly[1:]) for poly in polys if poly]  # (anillo exterior, huecos)
    if not productos or not poligonos:
        return None
    return {"cod": str(p.get("cod_zona") or ""), "n": n_zona, "productos": productos, "poligonos": poligonos}


def _pip(lon: float, lat: float, ring: list) -> bool:
    """Punto en polígono (ray casting) sobre un anillo [[lon, lat], ...]."""
    ins = False
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[i - 1][0], ring[i - 1][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            ins = not ins
    return ins


def _en_poligono(lon: float, lat: float, poligono: tuple[list, list]) -> bool:
    """Dentro del anillo exterior y fuera de sus huecos (un ámbito-isla no hereda el
    módulo del que lo envuelve)."""
    exterior, huecos = poligono
    return _pip(lon, lat, exterior) and not any(_pip(lon, lat, h) for h in huecos)


def _zona_del_punto(zonas: list[dict[str, Any]], lat: float, lon: float) -> dict[str, Any] | None:
    for z in zonas:
        if any(_en_poligono(lon, lat, pg) for pg in z["poligonos"]):
            return z
    return None


def _bbox(zonas: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    lons = [pt[0] for z in zonas for ext, _ in z["poligonos"] for pt in ext]
    lats = [pt[1] for z in zonas for ext, _ in z["poligonos"] for pt in ext]
    return min(lons), min(lats), max(lons), max(lats)


def _zona_con_respaldo(zonas: list[dict[str, Any]], lat: float, lon: float) -> dict[str, Any] | None:
    """Zona del punto; si no cae en ninguna (playa, borde), la más frecuente en anillos
    crecientes. Sin red: los polígonos ya están aquí."""
    z = _zona_del_punto(zonas, lat, lon)
    if z:
        return z
    for radius in _MAPA_RADII_M:
        hits = [h for h in (_zona_del_punto(zonas, la, lo) for la, lo in _ring_points(lat, lon, radius)) if h]
        if hits:
            cods = [h["cod"] for h in hits]
            best = max(set(cods), key=cods.count)
            return next(h for h in hits if h["cod"] == best)
    return None


def _mapa_fetch(lat: float, lon: float) -> dict[str, Any] | None:
    """Descarga los ámbitos del municipio del punto. Primero el mapa del año que viene
    (publicado desde finales de octubre), si viene vacío el del año en curso."""
    import datetime as _dt
    x, y = _merc(lon, lat)
    anyo_actual = _dt.date.today().year
    html = False
    for anyo in (anyo_actual + 1, anyo_actual):
        r = catastro_get(MAPA_VALORES, {"del": 0, "mun": 0, "huso": 3857, "x": x, "y": y, "suelo": "N",
                                        "tipo_mapa": "vivienda", "anyoZV": anyo}, timeout=_MAPA_TIMEOUT)
        try:
            feats = r.json().get("features") or []
        except ValueError:  # a veces contesta HTML en vez de JSON
            feats, html = [], True
        zonas = [z for z in (_zona_de_feature(f) for f in feats) if z]
        if zonas:
            p0 = feats[0].get("properties") or {}
            return {"anyo": anyo, "del": str(p0.get("id_delegacion") or ""), "mun": str(p0.get("id_municipio") or ""),
                    "zonas": zonas, "bbox": _bbox(zonas)}
    if html:  # sin JSON en ningún año: servicio caído, no «sin ámbito»
        raise RuntimeError("mapa de valores: respuesta HTML")
    return None


def _mapa_del_punto(lat: float, lon: float) -> dict[str, Any] | None:
    """Municipio (cacheado) cuyo mapa resuelve el punto (dentro de un ámbito o por el
    anillo de respaldo, dentro de su bbox); descarga si ninguno. Los puntos sin
    ámbito (mar, foral, gris) se recuerdan una hora para no re-descargar cada vez."""
    for data in _MAPA_CACHE.values():
        x0, y0, x1, y1 = data["bbox"]
        m = _MAPA_BBOX_MARGEN
        if x0 - m <= lon <= x1 + m and y0 - m <= lat <= y1 + m and _zona_con_respaldo(data["zonas"], lat, lon):
            return data
    clave = (round(lat, 3), round(lon, 3))
    if time.monotonic() - _MAPA_MISS.get(clave, -1e9) < _MAPA_MISS_TTL_S:
        return None
    data = _mapa_fetch(lat, lon)
    if data:
        _MAPA_CACHE[(data["del"], data["mun"])] = data
        if not _zona_con_respaldo(data["zonas"], lat, lon):
            _MAPA_MISS[clave] = time.monotonic()
    else:
        _MAPA_MISS[clave] = time.monotonic()
    return data


def _mapa_baseline(zonas: list[dict[str, Any]], clase: str) -> float | None:
    """Media del módulo de las zonas con producto de esa clase, ponderada por nº de
    viviendas = lo que el Notariado municipal/CP promedia. Función pura."""
    pares = [(p["m2"], p["n"]) for z in zonas for p in z["productos"] if p["clase"] == clase]
    peso = sum(n for _, n in pares)
    if not peso:
        return statistics.mean(m for m, _ in pares) if pares else None
    return sum(m * n for m, n in pares) / peso


@mcp.tool()
def mapa_valores_gradient(lat: float, lon: float, property_class: str = "") -> dict[str, Any]:
    """Gradiente de ubicación desde el mapa de valores de referencia: módulo €/m² del
    ámbito del inmueble ÷ media ponderada de los ámbitos del municipio con producto de
    la misma clase (piso / unifamiliar), amortiguado (**0.5) y acotado a ±30 %.

    {found: False} sin clase, sin ámbito o si el producto de la zona es de otra clase
    (→ el engine cae a la ponencia); además `error` si el Catastro no respondió.
    """
    if property_class not in ("piso", "unifamiliar"):
        return {"found": False, "gradient": 1.0}
    try:
        data = _mapa_del_punto(lat, lon)
    except Exception as exc:
        logger.warning("mapa_valores failed: %s", exc)
        return {"found": False, "gradient": 1.0, "error": True}
    if not data:
        return {"found": False, "gradient": 1.0}
    zona = _zona_con_respaldo(data["zonas"], lat, lon)
    prod = next((p for p in (zona or {}).get("productos", []) if p["clase"] == property_class), None)
    baseline = _mapa_baseline(data["zonas"], property_class) if prod else None
    if not prod or not baseline:
        return {"found": False, "gradient": 1.0, "reason": "clase" if zona and not prod else "sin_ambito"}
    bound = _MAPA_BOUND_GRANDE if len(data["zonas"]) > _MAPA_GRANDE else _BOUND
    return {
        "found": True,
        "gradient": round(_clamp_gradient(prod["m2"], baseline, bound=bound), 4),
        "bound": bound,
        "raw_gradient": round(prod["m2"] / baseline, 4),
        "subject": prod["m2"],
        "neighborhood_mean": round(baseline, 1),
        "zone_code": f"MV{zona['cod']}",
        "n": len(data["zonas"]),
        "anyo": data["anyo"],
        "tipologia": prod["tipologia"],
    }


if __name__ == "__main__":
    from mcp_servers._runtime import run_server
    run_server(mcp)

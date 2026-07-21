"""
IPV del INE (tabla Tempus3 79563, base 2025) — tendencia anual por CCAA.

El FeatureServer del Notariado es una FOTO (sin campo temporal; ventana de
agregación ~12 meses, último refresh visible en editingInfo). En un mercado
moviéndose a doble dígito anual (2026: +12.9% nacional), usar la mediana sin
reexpresar a "hoy" mete un sesgo sistemático a la baja. Este módulo da la
variación anual del Índice de Precios de Vivienda del INE por CCAA y por
tipo (general / nueva / segunda mano) para corregirlo.

⚠️ La tabla 25171 (base 2015) quedó HISTÓRICA el 2026-06-08, congelada en
2025T4 — seguía respondiendo datos, así que el ajuste temporal envejecía en
silencio. La vigente es la 79563 (base 2025), mismo contrato de series
("<CCAA>. <Tipo>. Variación anual."). Si el INE vuelve a rotar de base, el
self-check de contrato (valuation_api/test_ipv_contract.py) se pone en rojo
y la respuesta del motor marca `stale: true`.

API pública JSON del INE (sin key): DATOS_TABLA/79563?nult=1 devuelve, por
serie, el último dato trimestral. Cacheado en proceso 24 h (el IPV es
trimestral). Cualquier fallo → None (el motor lo trata como no-op, nunca
rompe una valoración).
"""
from __future__ import annotations

import logging
import time
import unicodedata
from typing import Any

import httpx

IPV_URL = "https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/79563"
HEADERS = {"User-Agent": "decomind-agent-challenge/0.1 (info@decomind.es)"}
TIMEOUT = 20.0
_TTL_S = 24 * 3600

logger = logging.getLogger("mcp.data_ipv")

# provincia (normalizada sin acentos, lowercase) → CCAA tal y como la nombra
# el INE en la tabla 79563. Cubre las 52 provincias + variantes bilingües.
_PROV_TO_CCAA = {
    # Andalucía
    "almeria": "Andalucía", "cadiz": "Andalucía", "cordoba": "Andalucía",
    "granada": "Andalucía", "huelva": "Andalucía", "jaen": "Andalucía",
    "malaga": "Andalucía", "sevilla": "Andalucía",
    # Aragón
    "huesca": "Aragón", "teruel": "Aragón", "zaragoza": "Aragón",
    # uniprovinciales
    "asturias": "Asturias, Principado de",
    "cantabria": "Cantabria",
    "illes balears": "Balears, Illes", "islas baleares": "Balears, Illes",
    "baleares": "Balears, Illes",
    "madrid": "Madrid, Comunidad de",
    "murcia": "Murcia, Región de",
    "navarra": "Navarra, Comunidad Foral de", "nafarroa": "Navarra, Comunidad Foral de",
    "la rioja": "Rioja, La", "rioja": "Rioja, La",
    # Canarias
    "las palmas": "Canarias", "santa cruz de tenerife": "Canarias",
    # Castilla y León
    "avila": "Castilla y León", "burgos": "Castilla y León",
    "leon": "Castilla y León", "palencia": "Castilla y León",
    "salamanca": "Castilla y León", "segovia": "Castilla y León",
    "soria": "Castilla y León", "valladolid": "Castilla y León",
    "zamora": "Castilla y León",
    # Castilla-La Mancha
    "albacete": "Castilla - La Mancha", "ciudad real": "Castilla - La Mancha",
    "cuenca": "Castilla - La Mancha", "guadalajara": "Castilla - La Mancha",
    "toledo": "Castilla - La Mancha",
    # Cataluña
    "barcelona": "Cataluña", "girona": "Cataluña", "gerona": "Cataluña",
    "lleida": "Cataluña", "lerida": "Cataluña", "tarragona": "Cataluña",
    # Comunitat Valenciana
    "alicante": "Comunitat Valenciana", "alacant": "Comunitat Valenciana",
    "castellon": "Comunitat Valenciana", "castello": "Comunitat Valenciana",
    "valencia": "Comunitat Valenciana",
    # Extremadura
    "badajoz": "Extremadura", "caceres": "Extremadura",
    # Galicia
    "a coruna": "Galicia", "la coruna": "Galicia", "coruna": "Galicia",
    "lugo": "Galicia", "ourense": "Galicia", "orense": "Galicia",
    "pontevedra": "Galicia",
    # País Vasco
    "alava": "País Vasco", "araba": "País Vasco",
    "bizkaia": "País Vasco", "vizcaya": "País Vasco",
    "gipuzkoa": "País Vasco", "guipuzcoa": "País Vasco",
    # ciudades autónomas
    "ceuta": "Ceuta", "melilla": "Melilla",
}

_SERIE_BY_CONSTRUCTION = {
    "nueva": "Vivienda nueva",
    "usada": "Vivienda segunda mano",
    "": "General",
}

# Caché de proceso: payload del INE + timestamp.
_cache: dict[str, Any] = {"at": 0.0, "items": None}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").strip().lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def ccaa_for_province(province: str) -> str | None:
    p = _norm(province)
    if p in _PROV_TO_CCAA:
        return _PROV_TO_CCAA[p]
    # nombres bilingües compuestos ("Castellón/Castelló", "Alacant / Alicante")
    for part in p.replace("/", " ").split():
        if part in _PROV_TO_CCAA:
            return _PROV_TO_CCAA[part]
    return None


def _fetch_items() -> list[dict] | None:
    now = time.time()
    if _cache["items"] is not None and now - _cache["at"] < _TTL_S:
        return _cache["items"]
    try:
        with httpx.Client(timeout=TIMEOUT, headers=HEADERS) as c:
            r = c.get(IPV_URL, params={"nult": 1})
            r.raise_for_status()
            items = r.json()
        if isinstance(items, list) and items:
            _cache.update(at=now, items=items)
            return items
    except Exception as exc:
        logger.warning("IPV fetch failed: %s", exc)
    return _cache["items"]  # payload viejo si lo hay; None si nunca hubo


def _quarter(fk_periodo: Any) -> int | None:
    """FK_Periodo de Tempus3 → trimestre 1-4 (19=T1 … 22=T4)."""
    return fk_periodo - 18 if isinstance(fk_periodo, int) and 19 <= fk_periodo <= 22 else None


def is_stale(anyo: Any, quarter: int | None, now: float | None = None) -> bool:
    """¿El último periodo publicado está rancio? Función pura (acepta `now`).

    El IPV publica con ~1 trimestre de retardo; >9 meses desde el FIN del
    trimestre = la tabla ha dejado de actualizarse (p. ej. rotación de base
    del INE, como la 25171 congelada en 2025T4).
    """
    try:
        year = int(anyo)
    except (TypeError, ValueError):
        return True
    if not quarter:
        return True
    end = time.mktime((year, quarter * 3 + 1, 1, 0, 0, 0, 0, 0, -1))
    return ((now or time.time()) - end) > 9 * 30 * 24 * 3600


def pick_trend(items: list[dict], ccaa: str | None,
               construction: str = "") -> dict[str, Any] | None:
    """Extrae la variación anual de la serie que toca. Función pura (testeable).

    Busca "<CCAA>. <Tipo>. Variación anual."; sin CCAA (provincia no mapeada)
    o sin serie de esa CCAA, cae a la nacional.
    """
    serie = _SERIE_BY_CONSTRUCTION.get(construction, "General")
    for scope in ([ccaa] if ccaa else []) + ["Nacional"]:
        prefix = _norm(f"{scope}. {serie}. Variación anual")
        for it in items:
            if _norm(it.get("Nombre", "")).startswith(prefix):
                data = it.get("Data") or []
                if data and data[0].get("Valor") is not None:
                    d = data[0]
                    q = _quarter(d.get("FK_Periodo"))
                    period = f"{d.get('Anyo', '')}T{q or d.get('FK_Periodo', '')}"
                    return {
                        "annual_pct": float(d["Valor"]),
                        "period": period,
                        "data_as_of": period,
                        "stale": is_stale(d.get("Anyo"), q),
                        "scope": scope,
                        "serie": serie,
                    }
    return None


def annual_trend(province: str, construction: str = "") -> dict[str, Any] | None:
    """Variación anual del IPV para la provincia (vía su CCAA) y tipo de vivienda.

    Devuelve {annual_pct, period, scope, serie} o None (sin red / sin dato) —
    el consumidor debe tratarlo como no-op.
    """
    items = _fetch_items()
    if not items:
        return None
    return pick_trend(items, ccaa_for_province(province), construction)

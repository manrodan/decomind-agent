"""
MCP server: Notariado — precio REAL de transacción ante notario.

Fuente: Portal Estadístico del Notariado (penotariado.com), que sirve los
datos vía un ArcGIS FeatureServer público. Son precios de COMPRAVENTAS REALES
formalizadas ante notario (Índice Único Notarial, 170M+ documentos),
anonimizados y agregados por zona geográfica.

Es el "gold standard" de valoración: precio real pagado, no oferta ni tasación.

Granularidad disponible (capas del FeatureServer):
  0 Nacional · 1 CCAA · 2 Provincia · 3 Municipio · 4 Código Postal

`notariado_price` hace fallback CP → municipio → provincia para máxima
cobertura, devolviendo el nivel usado y el nº de transacciones (fiabilidad).

Nota de uso: API REST pública de datos oficiales abiertos. Para uso intensivo
en producción conviene confirmar términos con el Consejo General del Notariado.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

ARCGIS = ("https://services-eu1.arcgis.com/UpPGybwp9RK4YtZj/arcgis/rest/"
          "services/PRO_Inmuebles_Datos/FeatureServer")
HEADERS = {"User-Agent": "decomind-agent-challenge/0.1 (info@decomind.es)"}
TIMEOUT = 15.0

# Segmentos del Índice Único Notarial (confirmados contra el FeatureServer vivo
# vía scripts/probe_notariado.py 4c/4d — el servicio NO publica coded-value
# domains, así que el mapeo se dedujo de los datos):
#   tipo_construccion_id:  7 = obra nueva · 9 = usada (2ª mano) · 99 = todas
#   clase_finca_urbana_id: 14 = vivienda colectiva (piso/ático) ·
#                          15 = unifamiliar (casa/chalet) · 99 = todas
# Evidencia: superficie_media de clase 14 ≈ 85-175 m² (pisos) vs clase 15 ≈
# 225-343 m² (unifamiliares); tipo 7 es minoritario y más caro (obra nueva).
_AGG = 99  # código "todas" (agregado)
_CLASE_CODES = {"piso": 14, "unifamiliar": 15}
_TIPO_CODES = {"nueva": 7, "usada": 9}
_CLASE_LABELS = {14: "piso", 15: "unifamiliar", _AGG: "todas"}
_TIPO_LABELS = {7: "nueva", 9: "usada", _AGG: "todas"}

# Mínimo de transacciones para fiarse del dato de un nivel; si no, baja de nivel.
MIN_TX = 15

logger = logging.getLogger("mcp.notariado")
mcp = FastMCP("notariado")


def _query(layer: int, where: str, out_fields: str) -> list[dict[str, Any]]:
    params = {
        "f": "json",
        "where": where,
        "outFields": out_fields,
        "returnGeometry": "false",
        "resultRecordCount": 5,
    }
    try:
        with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as c:
            r = c.get(f"{ARCGIS}/{layer}/query", params=params)
            r.raise_for_status()
            data = r.json()
        return [f.get("attributes", {}) for f in data.get("features", [])]
    except Exception as exc:
        logger.warning("Notariado layer %s query failed: %s", layer, exc)
        return []


def _pack(attrs: dict, level: str, geo_label: str,
          clase: int = _AGG, tipo: int = _AGG,
          requested_segment: bool = False) -> dict[str, Any]:
    is_agg = clase == _AGG and tipo == _AGG
    return {
        "found": True,
        "level": level,                # "codigo_postal" | "municipio" | "provincia"
        "geo": geo_label,
        "price_eur_per_m2": round(attrs.get("precio_m2") or 0, 1),
        "avg_price_eur": round(attrs.get("precio_medio") or 0),
        "avg_surface_m2": round(attrs.get("superficie_media") or 0, 1),
        "num_transactions": attrs.get("total") or 0,
        "num_reported": attrs.get("total_informados") or 0,
        "is_estimated": bool(attrs.get("es_estimado", 0)),
        # Qué segmento de inmueble respalda el precio (no "todas las viviendas").
        "segment": {
            "class": _CLASE_LABELS.get(clase, "todas"),         # piso | unifamiliar | todas
            "construction": _TIPO_LABELS.get(tipo, "todas"),    # nueva | usada | todas
        },
        # True si se pidió un segmento concreto pero hubo que caer al agregado
        # (muestra insuficiente) — el consumidor debe bajar la confianza.
        "segment_fallback": bool(requested_segment and is_agg),
        "source": "notariado",
        "source_label": "Consejo General del Notariado — compraventas reales ante notario",
    }


def _esc(s: str) -> str:
    return (s or "").replace("'", "''")


@mcp.tool()
def notariado_price(
    postal_code: str = "",
    municipality: str = "",
    province: str = "",
    property_class: str = "",
    construction: str = "",
) -> dict[str, Any]:
    """Precio REAL de transacción de vivienda (compraventas ante notario).

    Devuelve el €/m² real de las compraventas formalizadas ante notario en la
    zona, con el nº de transacciones que respaldan el dato. Hace fallback de
    granularidad fina a gruesa para máxima cobertura:
        código postal → municipio → provincia.

    Si se indica el segmento del inmueble (`property_class` / `construction`)
    consulta el precio de inmuebles SIMILARES (p. ej. solo pisos de 2ª mano) en
    vez del agregado "todas las viviendas". Como segmentar reduce la muestra,
    afloja primero el tipo (nueva/usada) y luego la clase (piso/unifamiliar),
    cayendo al agregado antes que devolver una muestra por debajo de MIN_TX.

    Args:
        postal_code: Código postal (5 dígitos). La granularidad más fina.
        municipality: Nombre del municipio (fallback si el CP no tiene dato).
        province: Nombre de la provincia (último fallback).
        property_class: "piso" | "unifamiliar" | "" (sin segmentar = agregado).
        construction: "nueva" | "usada" | "" (sin segmentar = agregado).

    Returns:
        {
          "found": bool,
          "level": "codigo_postal"|"municipio"|"provincia",
          "geo": str,                      # zona resuelta
          "price_eur_per_m2": float,       # PRECIO REAL de transacción
          "avg_price_eur": int,            # importe medio de compraventa
          "avg_surface_m2": float,
          "num_transactions": int,         # nº de ventas (fiabilidad)
          "is_estimated": bool,            # True si el dato es estimado por el Notariado
          "segment": {"class", "construction"},  # segmento que respalda el precio
          "segment_fallback": bool,        # True si se pidió segmento y cayó al agregado
          "source": "notariado",
          "source_label": str,
        }
        Si no hay dato en ningún nivel: {"found": False}.
    """
    # Guardrail: valida formato del CP (no bloquea el fallback a municipio).
    from mcp_servers._guardrails import validate_postal_code
    cp_error = validate_postal_code(postal_code)
    if cp_error and postal_code:
        postal_code = ""  # CP malformado → ignora, usa municipio/provincia

    out = ("precio_m2,precio_medio,superficie_media,total,total_informados,"
           "es_estimado")

    clase = _CLASE_CODES.get(property_class, _AGG)
    tipo = _TIPO_CODES.get(construction, _AGG)
    requested = clase != _AGG or tipo != _AGG

    # Candidatos de segmento, del más específico al agregado. Se preserva la
    # CLASE (piso vs unifamiliar) más que el TIPO (nueva/usada): la clase pesa
    # más en el precio y la muestra de obra nueva suele ser diminuta.
    candidates: list[tuple[int, int]] = []
    if requested:
        candidates.append((clase, tipo))
        if clase != _AGG and tipo != _AGG:
            candidates.append((clase, _AGG))   # afloja el tipo, conserva la clase
    candidates.append((_AGG, _AGG))            # agregado: siempre el último recurso

    def _where(cl: int, tp: int, geo: str) -> str:
        return (f"{geo} AND tipo_construccion_id={tp} "
                f"AND clase_finca_urbana_id={cl}")

    # Por cada segmento candidato baja CP → municipio exigiendo MIN_TX; el
    # primero que cumple gana (segmento más fino y con muestra suficiente).
    for cl, tp in candidates:
        if postal_code:
            rows = _query(4, _where(cl, tp, f"cp='{_esc(postal_code)}'"), out)
            if rows and (rows[0].get("total") or 0) >= MIN_TX:
                return _pack(rows[0], "codigo_postal", f"CP {postal_code}",
                             cl, tp, requested)
        if municipality:
            rows = _query(3, _where(cl, tp, f"name_muni='{_esc(municipality)}'"), out)
            if rows and (rows[0].get("total") or 0) >= MIN_TX:
                return _pack(rows[0], "municipio", municipality, cl, tp, requested)

    # Provincia: solo agregado (capa 2, sin segmento fino).
    if province:
        rows = _query(2, _where(_AGG, _AGG, f"name_prov='{_esc(province)}'"), out)
        if rows:
            return _pack(rows[0], "provincia", province, _AGG, _AGG, requested)

    # Último recurso: CP agregado aunque tenga pocas transacciones (algo > nada).
    if postal_code:
        rows = _query(4, _where(_AGG, _AGG, f"cp='{_esc(postal_code)}'"), out)
        if rows:
            r = _pack(rows[0], "codigo_postal", f"CP {postal_code}",
                      _AGG, _AGG, requested)
            r["low_sample"] = True
            return r

    return {"found": False, "reason": "no_data_any_level"}


if __name__ == "__main__":
    from mcp_servers._runtime import run_server
    run_server(mcp)

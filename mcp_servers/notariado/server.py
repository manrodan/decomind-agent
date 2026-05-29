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

# tipo_construccion_id=99 y clase_finca_urbana_id=99 = AGREGADO (todas las
# viviendas). Subtipos 7/9 y 14/15 quedan para filtrado fino en roadmap.
TOTAL_FILTER = "tipo_construccion_id=99 AND clase_finca_urbana_id=99"

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


def _pack(attrs: dict, level: str, geo_label: str) -> dict[str, Any]:
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
) -> dict[str, Any]:
    """Precio REAL de transacción de vivienda (compraventas ante notario).

    Devuelve el €/m² real de las compraventas formalizadas ante notario en la
    zona, con el nº de transacciones que respaldan el dato. Hace fallback de
    granularidad fina a gruesa para máxima cobertura:
        código postal → municipio → provincia.

    Args:
        postal_code: Código postal (5 dígitos). La granularidad más fina.
        municipality: Nombre del municipio (fallback si el CP no tiene dato).
        province: Nombre de la provincia (último fallback).

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

    # 1) Código postal (capa 4)
    if postal_code:
        rows = _query(4, f"cp='{_esc(postal_code)}' AND {TOTAL_FILTER}", out)
        if rows and (rows[0].get("total") or 0) >= MIN_TX:
            return _pack(rows[0], "codigo_postal", f"CP {postal_code}")

    # 2) Municipio (capa 3)
    if municipality:
        rows = _query(
            3, f"name_muni='{_esc(municipality)}' AND {TOTAL_FILTER}", out,
        )
        if rows and (rows[0].get("total") or 0) >= MIN_TX:
            return _pack(rows[0], "municipio", municipality)

    # 3) Provincia (capa 2)
    if province:
        rows = _query(
            2, f"name_prov='{_esc(province)}' AND {TOTAL_FILTER}", out,
        )
        if rows:
            return _pack(rows[0], "provincia", province)

    # 4) Reintento CP aunque tenga pocas transacciones (mejor algo que nada)
    if postal_code:
        rows = _query(4, f"cp='{_esc(postal_code)}' AND {TOTAL_FILTER}", out)
        if rows:
            r = _pack(rows[0], "codigo_postal", f"CP {postal_code}")
            r["low_sample"] = True
            return r

    return {"found": False, "reason": "no_data_any_level"}


if __name__ == "__main__":
    from mcp_servers._runtime import run_server
    run_server(mcp)

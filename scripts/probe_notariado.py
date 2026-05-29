"""
Probe del ArcGIS Feature Service del Portal Estadístico del Notariado.

El portal penotariado.com sirve los precios reales de transacción vía un
ArcGIS FeatureServer público (API REST estándar de Esri). Este probe inspecciona:
  1. Las capas del servicio (FeatureServer?f=json)
  2. El esquema de campos de la capa de datos (layer/3?f=json)
  3. Una muestra de datos reales (query con f=json, pocos registros)

Objetivo: ver qué campos hay (precio €/m², nº transacciones, granularidad
geográfica) para decidir si lo integramos como fuente de precio real.
"""

from __future__ import annotations

import json

import httpx

BASE = ("https://services-eu1.arcgis.com/UpPGybwp9RK4YtZj/arcgis/rest/"
        "services/PRO_Inmuebles_Datos/FeatureServer")
HEADERS = {"User-Agent": "Mozilla/5.0 decomind-agent/0.1"}


def get_json(url: str, params: dict) -> dict:
    with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as c:
        r = c.get(url, params=params)
        r.raise_for_status()
        return r.json()


def section(t: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {t}")
    print("=" * 72)


def main() -> None:
    # 1) capas del servicio
    section("1) Capas del FeatureServer")
    try:
        svc = get_json(BASE, {"f": "json"})
        for layer in svc.get("layers", []):
            print(f"  layer {layer.get('id')}: {layer.get('name')!r} ({layer.get('geometryType')})")
        for tbl in svc.get("tables", []):
            print(f"  table {tbl.get('id')}: {tbl.get('name')!r}")
    except Exception as exc:
        print(f"ERROR: {exc}")

    # 2) esquema de campos de la capa 3
    section("2) Campos de la capa 3 (PRO_Inmuebles_Datos / layer 3)")
    try:
        meta = get_json(f"{BASE}/3", {"f": "json"})
        print(f"  name: {meta.get('name')!r}")
        print(f"  geometryType: {meta.get('geometryType')}")
        print(f"  campos:")
        for fld in meta.get("fields", []):
            print(f"    {fld.get('name'):30} {fld.get('type'):24} {fld.get('alias','')}")
    except Exception as exc:
        print(f"ERROR: {exc}")

    # 3) campos de la capa 4 (Código Postal)
    section("3) Campos de la capa 4 (Código Postal)")
    cp_field = None
    try:
        meta4 = get_json(f"{BASE}/4", {"f": "json"})
        print(f"  name: {meta4.get('name')!r}")
        for fld in meta4.get("fields", []):
            print(f"    {fld.get('name'):30} {fld.get('type')}")
            n = fld.get("name", "").lower()
            if "postal" in n or n in ("cp", "cod_cp", "codigo_postal"):
                cp_field = fld.get("name")
    except Exception as exc:
        print(f"ERROR: {exc}")

    # 4) valores distintos de tipo_construccion_id y clase_finca_urbana_id
    section("4) Valores distintos de tipo_construccion_id (capa 3)")
    try:
        d = get_json(f"{BASE}/3/query", {
            "f": "json",
            "where": "1=1",
            "outFields": "tipo_construccion_id",
            "returnDistinctValues": "true",
            "returnGeometry": "false",
        })
        vals = sorted({ft["attributes"]["tipo_construccion_id"] for ft in d.get("features", [])})
        print(f"  tipo_construccion_id: {vals}")
    except Exception as exc:
        print(f"ERROR: {exc}")

    section("4b) Valores distintos de clase_finca_urbana_id (capa 3)")
    try:
        d = get_json(f"{BASE}/3/query", {
            "f": "json",
            "where": "1=1",
            "outFields": "clase_finca_urbana_id",
            "returnDistinctValues": "true",
            "returnGeometry": "false",
        })
        vals = sorted({ft["attributes"]["clase_finca_urbana_id"] for ft in d.get("features", [])})
        print(f"  clase_finca_urbana_id: {vals}")
    except Exception as exc:
        print(f"ERROR: {exc}")

    # 5) query Madrid municipio con total (99,99) para ver el agregado
    section("5) Madrid municipio — agregado total (tipo=99, clase=99)")
    try:
        q = get_json(f"{BASE}/3/query", {
            "f": "json",
            "where": "name_muni='Madrid' AND tipo_construccion_id=99 AND clase_finca_urbana_id=99",
            "outFields": "name_muni,precio_m2,precio_medio,superficie_media,total,total_informados,es_estimado",
            "returnGeometry": "false",
        })
        print(json.dumps(q.get("features", []), indent=2, ensure_ascii=False))
    except Exception as exc:
        print(f"ERROR: {exc}")

    # 6) query por código postal 28013 en capa 4 (si encontramos el campo)
    section("6) Código Postal 28013 — capa 4")
    try:
        where_cp = f"{cp_field}='28013'" if cp_field else "1=1"
        q = get_json(f"{BASE}/4/query", {
            "f": "json",
            "where": where_cp + " AND tipo_construccion_id=99 AND clase_finca_urbana_id=99",
            "outFields": "*",
            "resultRecordCount": 3,
            "returnGeometry": "false",
        })
        print(f"  (campo CP detectado: {cp_field})")
        print(json.dumps(q.get("features", []), indent=2, ensure_ascii=False)[:2000])
    except Exception as exc:
        print(f"ERROR: {exc}")


if __name__ == "__main__":
    main()

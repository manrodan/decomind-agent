"""
Snapshot mensual del FeatureServer del Notariado — serie temporal PROPIA.

El FeatureServer (PRO_Inmuebles_Datos) es una FOTO sin dimensión temporal:
cada refresh pisa la anterior. Archivando un volcado mensual construimos
nuestra propia serie de precios por CP y municipio — en 6-12 meses el ajuste
temporal podrá usar la tendencia REAL del propio código postal en vez del
IPV por CCAA (regional y grueso).

Uso (una vez al MES, local):
    .venv\\Scripts\\python.exe -m scripts.snapshot_notariado

Salida: data/notariado_snapshots/YYYY-MM.json.gz (commiteable, ~2-4 MB).
Idempotente: si el fichero del mes ya existe, no hace nada (--force para
repetir). Sin geometrías (returnGeometry=false): solo atributos.
"""
from __future__ import annotations

import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ARCGIS = ("https://services-eu1.arcgis.com/UpPGybwp9RK4YtZj/arcgis/rest/"
          "services/PRO_Inmuebles_Datos/FeatureServer")
HEADERS = {"User-Agent": "decomind-agent-challenge/0.1 (info@decomind.es)"}
TIMEOUT = 60.0
PAGE = 2000  # maxRecordCount del servicio

# Capas con valor de serie: CP (la que usa el motor) + Municipio (shrinkage).
LAYERS = {"codigo_postal": 4, "municipio": 3}

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "notariado_snapshots"


def _dump_layer(client: httpx.Client, layer_id: int) -> list[dict]:
    """Todas las features de la capa (todos los segmentos tipo×clase), paginado."""
    rows: list[dict] = []
    offset = 0
    while True:
        r = client.get(f"{ARCGIS}/{layer_id}/query", params={
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "false",
            "resultOffset": offset,
            "resultRecordCount": PAGE,
            "f": "json",
        })
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"ArcGIS error en capa {layer_id}: {data['error']}")
        feats = data.get("features") or []
        for f in feats:
            attrs = f.get("attributes") or {}
            # Shape__Area/Length no aportan a la serie y pesan.
            rows.append({k: v for k, v in attrs.items()
                         if not k.startswith("Shape__")})
        if not feats or not data.get("exceededTransferLimit"):
            break
        offset += len(feats)
    return rows


def main() -> None:
    force = "--force" in sys.argv
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{month}.json.gz"
    if out.exists() and not force:
        print(f"Ya existe {out.name} — snapshot mensual hecho (usa --force para repetir).")
        return

    snapshot: dict = {
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": ARCGIS,
        "layers": {},
    }
    with httpx.Client(timeout=TIMEOUT, headers=HEADERS) as client:
        for name, layer_id in LAYERS.items():
            rows = _dump_layer(client, layer_id)
            snapshot["layers"][name] = rows
            print(f"{name}: {len(rows)} filas")

    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(snapshot, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"Escrito {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()

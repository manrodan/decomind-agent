"""
Backtest ESTRUCTURAL del motor contra idealista18 (Madrid/Barcelona/Valencia).

Qué mide y qué NO:
  - idealista18 (paezha/idealista18, paper EPB 2024) son ~190k anuncios de
    2018 con precio de OFERTA. Ni son cierres ni son de hoy, así que el NIVEL
    absoluto no es comparable: se corrige con un factor de escala por ciudad
    (k = mediana(real/predicho)) que absorbe a la vez el salto 2018→hoy y la
    prima oferta-vs-cierre.
  - Lo que queda tras corregir el nivel es la precisión ESTRUCTURAL del
    motor: curva de superficie, hedónico y micro-ubicación. MdAPE/PPE10/PPE20
    post-escala + sesgo por tramo de superficie. Es la vara de medir para
    cambios del modelo (congelada en evals/backtest_baseline.json), NO una
    cifra de precisión comercial.

Pipeline por muestra (espejo del engine, sin geocoding de dirección ni
Catastro — el dataset ya trae coordenada y año catastral):
  reverse geocode coord→CP (Nominatim, caché en disco, 1 req/s)
  → notariado_price segmentado (piso, nueva/usada, con shrinkage)
  → estimate_market_value (hedónico v2, superficie relativa)
  → micro-ubicación (zona de valor × sección censal, media geométrica)

Uso:
  .venv\\Scripts\\python.exe -m evals.backtest              # 100 muestras/ciudad
  .venv\\Scripts\\python.exe -m evals.backtest --n 50       # más rápido
  .venv\\Scripts\\python.exe -m evals.backtest --no-micro   # sin micro-ubicación

Requiere: pip install rdata  +  scripts de datos en data/raw/idealista18/
(descarga: curl -L -o data/raw/idealista18/<City>_Sale.rda
 https://github.com/paezha/idealista18/raw/master/data/<City>_Sale.rda)
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_servers.notariado.server import notariado_price  # noqa: E402
from mcp_servers.market_research.server import estimate_market_value  # noqa: E402
from mcp_servers.seccion_censal.server import (  # noqa: E402
    seccion_lookup, seccion_signal_gradient,
)
from mcp_servers.zona_valor.server import zona_valor_gradient  # noqa: E402
from valuation_api.engine import MODEL_VERSION, _combine_gradients  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "idealista18"
CACHE_PATH = DATA_DIR / "geo_cache.json"
OUT_PATH = Path(__file__).resolve().parent / "backtest_baseline.json"

CITIES = {
    "Madrid": {"file": "Madrid_Sale.rda", "province": "Madrid", "municipality": "Madrid"},
    "Barcelona": {"file": "Barcelona_Sale.rda", "province": "Barcelona", "municipality": "Barcelona"},
    "Valencia": {"file": "Valencia_Sale.rda", "province": "Valencia", "municipality": "Valencia"},
}
_FLOOR_UNKNOWN = -999
_NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
_UA = {"User-Agent": "decomind-agent-challenge/0.1 (info@decomind.es)"}

_TRANCHES = [(0, 50), (50, 80), (80, 120), (120, 10_000)]


def _load_city(fname: str):
    import rdata  # import diferido: dependencia solo del backtest
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # constructores sf ausentes: irrelevante
        res = rdata.read_rda(str(DATA_DIR / fname))
    return res[next(iter(res))]


def _sample(df, n: int):
    """Muestra determinista: ordena por ASSETID y toma filas equiespaciadas."""
    df = df.sort_values("ASSETID").reset_index(drop=True)
    if len(df) <= n:
        return df
    step = len(df) / n
    idx = [int(i * step) for i in range(n)]
    return df.iloc[idx]


def _geo_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _reverse_cp(lat: float, lon: float, cache: dict) -> str | None:
    key = f"{lat:.5f},{lon:.5f}"
    if key in cache:
        return cache[key] or None
    try:
        with httpx.Client(timeout=20, headers=_UA) as c:
            r = c.get(_NOMINATIM, params={
                "lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18})
            r.raise_for_status()
            cp = ((r.json().get("address") or {}).get("postcode") or "").strip()
    except Exception:
        cp = ""
    cache[key] = cp
    time.sleep(1.1)  # política de uso de Nominatim: máx 1 req/s
    return cp or None


def _row_inputs(row) -> dict:
    """Fila idealista18 → kwargs hedónicos del motor (sentinels MCP)."""
    b = lambda col: bool(row.get(col)) and float(row.get(col) or 0) > 0
    if b("BUILTTYPEID_1"):
        condition = "obra_nueva"
    elif b("BUILTTYPEID_2"):
        condition = "a_reformar"
    else:
        condition = "buen_estado"
    orientation = ("sur" if b("HASSOUTHORIENTATION") else
                   "este" if b("HASEASTORIENTATION") else
                   "oeste" if b("HASWESTORIENTATION") else
                   "norte" if b("HASNORTHORIENTATION") else "")
    floor = row.get("FLOORCLEAN")
    try:
        floor = int(floor) if floor is not None and not math.isnan(float(floor)) else None
    except (TypeError, ValueError):
        floor = None
    year = row.get("CADCONSTRUCTIONYEAR")
    try:
        year = int(year) if year and 1800 < float(year) <= 2018 else 0
    except (TypeError, ValueError):
        year = 0
    return {
        "condition": condition,
        "construction": "nueva" if condition == "obra_nueva" else "usada",
        "year_built": year,
        "floor": _FLOOR_UNKNOWN if floor is None else floor,
        "has_elevator": 1 if b("HASLIFT") else 0,
        "is_attic": b("ISINTOPFLOOR"),
        "orientation": orientation,
        "bedrooms": int(row.get("ROOMNUMBER") or 0),
        "bathrooms": int(row.get("BATHNUMBER") or 0),
        "has_terrace": b("HASTERRACE"),
        "has_garage": b("HASPARKINGSPACE") and b("ISPARKINGSPACEINCLUDEDINPRICE"),
        "has_storage_room": b("HASBOXROOM"),
        "has_pool": b("HASSWIMMINGPOOL"),
    }


def _predict(row, city_cfg: dict, cp: str, use_micro: bool) -> float | None:
    surface = float(row.get("CONSTRUCTEDAREA") or 0)
    if not surface:
        return None
    inp = _row_inputs(row)
    nota = notariado_price(
        postal_code=cp, municipality=city_cfg["municipality"],
        province=city_cfg["province"], property_class="piso",
        construction=inp["construction"])
    if not nota.get("found") or not nota.get("price_eur_per_m2"):
        return None
    # Espejo de la regla v2.8.0 del engine: base ya segmentada 'nueva' →
    # estado neutro (evita contar la prima de obra nueva dos veces). El
    # harness DEBE replicar el pipeline de producción o mide otro motor.
    condition = inp["condition"]
    if (condition == "obra_nueva"
            and (nota.get("segment") or {}).get("construction") == "nueva"):
        condition = "buen_estado"
    val = estimate_market_value(
        surface_m2=surface,
        median_price_eur_per_m2=nota["price_eur_per_m2"],
        condition=condition,
        year_built=inp["year_built"],
        zone_avg_surface_m2=nota.get("avg_surface_m2") or 0,
        zone_typical_year=0,
        floor=inp["floor"],
        has_elevator=inp["has_elevator"],
        is_attic=inp["is_attic"],
        energy_rating="",
        exterior=-1,
        orientation=inp["orientation"],
        bedrooms=inp["bedrooms"],
        bathrooms=inp["bathrooms"],
        has_terrace=inp["has_terrace"],
        has_garage=inp["has_garage"],
        has_storage_room=inp["has_storage_room"],
        has_pool=inp["has_pool"],
    )
    pred = val.get("value_eur")
    if not pred:
        return None
    if use_micro:
        lat, lon = float(row["LATITUDE"]), float(row["LONGITUDE"])
        try:
            grad = zona_valor_gradient(lat=lat, lon=lon)
        except Exception:
            grad = {"found": False}
        try:
            sec0 = seccion_lookup(lat, lon)
            sec = seccion_signal_gradient(
                lat=lat, lon=lon, cusec=sec0.get("cusec") or "",
                cumun=sec0.get("cumun") or "") if sec0.get("found") else {"found": False}
        except Exception:
            sec = {"found": False}
        g = _combine_gradients([
            grad.get("gradient") if grad.get("found") else None,
            sec.get("gradient") if sec.get("found") else None,
        ])
        pred *= g
    return float(pred)


def _metrics(pairs: list[tuple[float, float]]) -> dict:
    """pairs = [(real, predicho_sin_escala)] de UNA ciudad."""
    k = median(a / p for a, p in pairs)
    apes = [abs((p * k - a) / a) for a, p in pairs]
    return {
        "n": len(pairs),
        "scale_k": round(k, 4),
        "mdape_pct": round(median(apes) * 100, 1),
        "ppe10_pct": round(100 * sum(x <= 0.10 for x in apes) / len(apes), 1),
        "ppe20_pct": round(100 * sum(x <= 0.20 for x in apes) / len(apes), 1),
    }


def main() -> None:
    n = 100
    use_micro = "--no-micro" not in sys.argv
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])

    cache = _geo_cache()
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_version": MODEL_VERSION,
        "dataset": "idealista18 (asking prices 2018 — backtest estructural, nivel corregido por ciudad)",
        "micro_location": use_micro,
        "sample_per_city": n,
        "cities": {},
    }
    all_tranche_pes: dict[str, list[float]] = {}

    for city, cfg in CITIES.items():
        path = DATA_DIR / cfg["file"]
        if not path.exists():
            print(f"[{city}] falta {path.name} — descárgalo (ver docstring). Saltada.")
            continue
        df = _sample(_load_city(cfg["file"]), n)
        pairs: list[tuple[float, float]] = []
        surfaces: list[float] = []
        skipped = 0
        for i, (_, row) in enumerate(df.iterrows(), 1):
            cp = _reverse_cp(float(row["LATITUDE"]), float(row["LONGITUDE"]), cache)
            if i % 25 == 0:
                CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
                print(f"  [{city}] {i}/{len(df)}…")
            if not cp:
                skipped += 1
                continue
            try:
                pred = _predict(row, cfg, cp, use_micro)
            except Exception:
                pred = None
            actual = float(row.get("PRICE") or 0)
            if not pred or not actual:
                skipped += 1
                continue
            pairs.append((actual, pred))
            surfaces.append(float(row.get("CONSTRUCTEDAREA") or 0))
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
        if len(pairs) < 20:
            print(f"[{city}] solo {len(pairs)} muestras válidas — sin métricas.")
            continue
        m = _metrics(pairs)
        m["skipped"] = skipped
        # Sesgo estructural por tramo de superficie (post-escala): si el motor
        # infra/sobre-valora sistemáticamente pisos pequeños o grandes.
        k = m["scale_k"]
        tranche_bias = {}
        for lo, hi in _TRANCHES:
            pes = [(p * k - a) / a for (a, p), s in zip(pairs, surfaces) if lo <= s < hi]
            label = f"{lo}-{hi if hi < 10_000 else '+'} m2"
            if len(pes) >= 8:
                tranche_bias[label] = round(median(pes) * 100, 1)
                all_tranche_pes.setdefault(label, []).extend(pes)
        m["bias_by_surface_tranche_pct"] = tranche_bias
        report["cities"][city] = m
        print(f"[{city}] n={m['n']} MdAPE={m['mdape_pct']}% "
              f"PPE10={m['ppe10_pct']}% PPE20={m['ppe20_pct']}% k={m['scale_k']}")

    if report["cities"]:
        report["global"] = {
            "mdape_pct": round(median(
                m["mdape_pct"] for m in report["cities"].values()), 1),
            "bias_by_surface_tranche_pct": {
                t: round(median(v) * 100, 1) for t, v in sorted(all_tranche_pes.items())
                if len(v) >= 15},
        }
        OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        print(f"\nBaseline escrito en {OUT_PATH}")
    else:
        print("Sin resultados: ¿faltan los .rda?")


if __name__ == "__main__":
    main()

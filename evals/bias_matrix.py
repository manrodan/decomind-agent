"""
Matriz de sesgos por TIPOLOGÍA — detección sistemática de factores hedónicos
descalibrados, contra idealista18 (mismo marco que evals/backtest.py: nivel
2018→hoy corregido por factor k por ciudad; lo que queda es estructura).

El backtest reveló el sesgo de Madrid <50 m² (+18%). Los 8 factores del
hedónico se fijaron con heurísticas, así que cualquiera puede llevar un sesgo
equivalente para su tipología. Este script saca la foto completa: sesgo
mediano (PE post-escala) y MdAPE por categoría, por ciudad y global, con
sobremuestreo de las tipologías escasas (<50 m², ático, a_reformar, obra
nueva) para que ninguna quede sin medir.

Uso:
  .venv\\Scripts\\python.exe -m evals.bias_matrix            # 250/ciudad + boosts
  .venv\\Scripts\\python.exe -m evals.bias_matrix --n 120    # más rápido

Salida: evals/bias_matrix.json + tabla en consola.
Reutiliza loader/geocode-caché/predicción de evals/backtest.py.
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals.backtest import (  # noqa: E402
    CITIES, DATA_DIR, CACHE_PATH, _geo_cache, _load_city, _predict,
    _reverse_cp, _row_inputs, _sample,
)
from valuation_api.engine import MODEL_VERSION  # noqa: E402

OUT_PATH = Path(__file__).resolve().parent / "bias_matrix.json"

# Categorías escasas que se sobremuestrean (mask sobre el DataFrame crudo).
_BOOSTS = {
    "menos_50m2": lambda df: df["CONSTRUCTEDAREA"] < 50,
    "atico": lambda df: df["ISINTOPFLOOR"] > 0,
    "a_reformar": lambda df: df["BUILTTYPEID_2"] > 0,
    "obra_nueva": lambda df: df["BUILTTYPEID_1"] > 0,
}
_BOOST_N = 40


def _floor_of(row) -> int | None:
    f = row.get("FLOORCLEAN")
    try:
        return int(f) if f is not None and not math.isnan(float(f)) else None
    except (TypeError, ValueError):
        return None


def _categories(row) -> list[str]:
    """Etiquetas de tipología de una fila (una fila puntúa en varias)."""
    cats: list[str] = []
    s = float(row.get("CONSTRUCTEDAREA") or 0)
    cats.append("sup <50 m²" if s < 50 else "sup 50-80 m²" if s < 80
                else "sup 80-120 m²" if s < 120 else "sup >120 m²")
    inp = _row_inputs(row)
    floor = _floor_of(row)
    if floor is not None:
        if floor >= 3:
            cats.append("planta ≥3 con ascensor" if inp["has_elevator"]
                        else "planta ≥3 SIN ascensor")
        elif floor <= 1:
            cats.append("planta baja/1ª")
    if inp["is_attic"]:
        cats.append("ático")
    cats.append("con terraza" if inp["has_terrace"] else "sin terraza")
    cats.append({"obra_nueva": "estado: obra nueva",
                 "a_reformar": "estado: a reformar",
                 "buen_estado": "estado: buen estado"}[inp["condition"]])
    y = inp["year_built"]
    if y:
        cats.append("año <1950" if y < 1950 else "año 1950-80" if y < 1980
                    else "año 1980-2005" if y < 2005 else "año >2005")
    if inp["has_garage"]:
        cats.append("garaje incluido")
    if inp["has_storage_room"]:
        cats.append("trastero")
    return cats


def _stratified(df, n: int):
    """Muestra equiespaciada + boost de categorías escasas (dedupe ASSETID)."""
    base = _sample(df, n)
    seen = set(base["ASSETID"])
    frames = [base]
    for name, mask_fn in _BOOSTS.items():
        try:
            pool = df[mask_fn(df)].sort_values("ASSETID")
        except KeyError:
            continue
        pool = pool[~pool["ASSETID"].isin(seen)]
        extra = _sample(pool, _BOOST_N) if len(pool) else pool
        seen.update(extra["ASSETID"])
        frames.append(extra)
    import pandas as pd
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    n = 250
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])
    use_micro = "--no-micro" not in sys.argv

    cache = _geo_cache()
    # point = (city, actual, pred, cats)
    points: list[tuple[str, float, float, list[str]]] = []
    for city, cfg in CITIES.items():
        path = DATA_DIR / cfg["file"]
        if not path.exists():
            print(f"[{city}] falta {path.name} — saltada.")
            continue
        df = _stratified(_load_city(cfg["file"]), n)
        done = skipped = 0
        for i, (_, row) in enumerate(df.iterrows(), 1):
            cp = _reverse_cp(float(row["LATITUDE"]), float(row["LONGITUDE"]), cache)
            if i % 50 == 0:
                CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
                print(f"  [{city}] {i}/{len(df)}…")
            actual = float(row.get("PRICE") or 0)
            if not cp or not actual:
                skipped += 1
                continue
            try:
                pred = _predict(row, cfg, cp, use_micro)
            except Exception:
                pred = None
            if not pred:
                skipped += 1
                continue
            points.append((city, actual, pred, _categories(row)))
            done += 1
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
        print(f"[{city}] {done} válidas · {skipped} saltadas")

    if not points:
        print("Sin datos.")
        return

    # k por ciudad sobre TODA su muestra → PE post-escala por punto.
    ks = {city: median(a / p for c, a, p, _ in points if c == city)
          for city in {c for c, *_ in points}}
    pes: list[tuple[str, float, list[str]]] = [
        (c, (p * ks[c] - a) / a, cats) for c, a, p, cats in points]

    def _agg(rows: list[float]) -> dict:
        return {"n": len(rows),
                "bias_pct": round(median(rows) * 100, 1),
                "mdape_pct": round(median(abs(x) for x in rows) * 100, 1)}

    all_cats = sorted({cat for _, _, cats in pes for cat in cats})
    matrix: dict[str, dict] = {}
    for cat in all_cats:
        rows = [pe for _, pe, cats in pes if cat in cats]
        if len(rows) < 15:
            continue
        entry = _agg(rows)
        per_city = {}
        for city in sorted(ks):
            crows = [pe for c, pe, cats in pes if c == city and cat in cats]
            if len(crows) >= 12:
                per_city[city] = _agg(crows)
        entry["by_city"] = per_city
        matrix[cat] = entry

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_version": MODEL_VERSION,
        "dataset": "idealista18 — sesgo estructural post-escala por tipología",
        "micro_location": use_micro,
        "scale_k": {c: round(k, 4) for c, k in ks.items()},
        "total_points": len(points),
        "matrix": matrix,
    }
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    print(f"\n{'categoría':<28}{'n':>5}{'sesgo':>8}{'MdAPE':>8}   por ciudad (sesgo)")
    for cat, m in matrix.items():
        cities_txt = " · ".join(f"{c[:3]} {v['bias_pct']:+.1f}%"
                                for c, v in m["by_city"].items())
        print(f"{cat:<28}{m['n']:>5}{m['bias_pct']:>+7.1f}%{m['mdape_pct']:>7.1f}%   {cities_txt}")
    print(f"\nEscrito {OUT_PATH}")


if __name__ == "__main__":
    main()

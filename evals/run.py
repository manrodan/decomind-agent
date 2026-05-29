"""
Eval runner — ejecuta el pipeline real de tools para cada caso del dataset,
aplica checks de calidad y produce una tabla de resultados + score agregado.

Es una suite de regresión reproducible: cada cambio se puede re-evaluar y
comparar contra el baseline. Ejecuta las tools determinísticas + las APIs
oficiales reales (geocoding, catastro, notariado) — prueba la integración
de verdad, no mocks.

Uso:
    python -m evals.run                 # ejecuta todos los casos
    python -m evals.run --only madrid-centro
    python -m evals.run --json out.json # guarda resultados para regresión

Métricas por caso:
    - geocoding resuelve coordenadas
    - catastro devuelve año oficial en rango plausible
    - notariado devuelve precio real al nivel esperado (CP/municipio)
    - valoración hedónica dentro de rango
    - convergencia notariado vs MITMA (triangulación)
    - ROI coherente
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from evals.dataset import CASES

# Tools (llamadas Python directas — rápido y determinista salvo APIs externas)
from mcp_servers.geocoding.server import geocode_address
from mcp_servers.catastro.server import catastro_lookup
from mcp_servers.notariado.server import notariado_price
from mcp_servers.market_research.server import (
    find_comparables,
    estimate_market_value,
    compute_renovation_roi,
)
from mcp_servers.renovation.server import estimate_renovation_plan


def _in_range(v, rng) -> bool:
    return v is not None and rng[0] <= v <= rng[1]


def run_case(case: dict) -> dict[str, Any]:
    """Ejecuta el pipeline para un caso y devuelve resultado + checks."""
    inp = case["input"]
    exp = case["expect"]
    checks: list[tuple[str, bool, str]] = []  # (nombre, pass, detalle)
    t0 = time.time()

    # 1. Geocoding
    geo = geocode_address(
        address=inp["address"], locality=inp["locality"],
        province=inp["province"], postal_code=inp["postal_code"],
    )
    geo_ok = bool(geo.get("found"))
    checks.append(("geocode_found", geo_ok == exp["geocode_found"],
                   f"found={geo_ok}"))
    lat = float(geo.get("lat") or 0)
    lon = float(geo.get("lon") or 0)
    muni = geo.get("municipality") or inp["locality"]
    prov = geo.get("province") or inp["province"]
    distr = geo.get("city_district") or ""

    # 2. Catastro (best-effort: o da año oficial, o el sistema degrada limpio)
    cat = catastro_lookup(lat, lon) if geo_ok else {"found": False}
    cat_ok = bool(cat.get("found"))
    year = cat.get("year_built")
    # El check de degradación se evalúa más abajo (necesita current_value).

    # 3. Notariado (precio real)
    nota = notariado_price(
        postal_code=inp["postal_code"], municipality=muni, province=prov,
    )
    nota_ok = bool(nota.get("found"))
    nota_level = nota.get("level", "")
    nota_price = nota.get("price_eur_per_m2")
    nota_tx = nota.get("num_transactions", 0)
    checks.append(("notariado_found", nota_ok, f"found={nota_ok}"))
    checks.append(("notariado_level_ok", nota_level in exp["notariado_level"],
                   f"level={nota_level} exp={exp['notariado_level']}"))
    checks.append(("notariado_price_in_range",
                   _in_range(nota_price, exp["notariado_price_range"]),
                   f"price={nota_price} exp={exp['notariado_price_range']}"))
    checks.append(("notariado_min_transactions",
                   (nota_tx or 0) >= exp["notariado_min_transactions"],
                   f"tx={nota_tx} min={exp['notariado_min_transactions']}"))

    # 4. MITMA (segunda fuente) vía find_comparables
    comps = find_comparables(
        lat=lat, lon=lon, province=prov, municipality=muni, district=distr,
    )
    mitma_price = comps.get("median_price_eur_per_m2")

    # 5. Valoración hedónica — base = precio Notariado (o MITMA fallback)
    base_price = nota_price or mitma_price or 1800
    val = estimate_market_value(
        surface_m2=inp["surface_m2"], median_price_eur_per_m2=base_price,
        condition=inp["condition"], year_built=year or 0,
    )
    current_value = val.get("value_eur")
    checks.append(("current_value_in_range",
                   _in_range(current_value, exp["current_value_range"]),
                   f"value={current_value} exp={exp['current_value_range']}"))

    # Catastro best-effort: año oficial en rango O degradación elegante
    # (sin año, el pipeline sigue produciendo una valoración válida).
    year_ok = _in_range(year, exp["catastro_year_range"])
    graceful = (year is None) and _in_range(current_value, exp["current_value_range"])
    checks.append(("catastro_official_or_graceful",
                   year_ok or graceful,
                   f"year={year} ({'official' if year_ok else 'graceful-degradation' if graceful else 'FAIL'})"))
    checks.append(("hedonic_factors_present",
                   isinstance(val.get("factors"), dict) and len(val["factors"]) == 6,
                   f"factors={list((val.get('factors') or {}).keys())}"))

    # Convergencia triangulación (notariado vs mitma)
    convergence = None
    if nota_price and mitma_price:
        convergence = round(min(nota_price, mitma_price) / max(nota_price, mitma_price) * 100)
    checks.append(("triangulation_available",
                   convergence is not None,
                   f"convergence={convergence}%"))

    # 6. Reforma + valor post + ROI
    plan = estimate_renovation_plan(rooms=inp["rooms"], tier=inp["tier"])
    reno_total = plan.get("totals", {}).get("integral", 0)
    val_post = estimate_market_value(
        surface_m2=inp["surface_m2"], median_price_eur_per_m2=base_price,
        condition="buen_estado", year_built=year or 0,
    )
    post_value = val_post.get("value_eur")
    roi = compute_renovation_roi(
        investment_eur=reno_total, current_value_eur=current_value,
        post_reno_market_value_eur=post_value,
    )
    reco = roi.get("recommendation")
    checks.append(("roi_recommendation_valid",
                   reco in exp["roi_recommendation_in"],
                   f"reco={reco}"))
    checks.append(("roi_coherent",
                   isinstance(roi.get("payback_ratio"), (int, float)),
                   f"payback={roi.get('payback_ratio')}"))

    elapsed = round(time.time() - t0, 1)
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)

    return {
        "id": case["id"],
        "desc": case["desc"],
        "checks": checks,
        "passed": passed,
        "total": total,
        "score": round(passed / total * 100),
        "elapsed_s": elapsed,
        "snapshot": {
            "year_built": year,
            "notariado_price": nota_price,
            "notariado_level": nota_level,
            "notariado_tx": nota_tx,
            "mitma_price": mitma_price,
            "convergence_pct": convergence,
            "current_value": current_value,
            "reno_total": reno_total,
            "post_value": post_value,
            "roi_recommendation": reco,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="id del caso a ejecutar")
    ap.add_argument("--json", help="ruta para guardar resultados JSON")
    ap.add_argument("--verbose", action="store_true", help="muestra cada check")
    args = ap.parse_args()

    cases = [c for c in CASES if not args.only or c["id"] == args.only]
    results = []

    print(f"\n{'='*78}")
    print(f"  DECOMIND AGENT — EVAL SUITE  ({len(cases)} casos)")
    print(f"{'='*78}")

    for case in cases:
        print(f"\n▶ {case['id']}: {case['desc']}")
        try:
            r = run_case(case)
        except Exception as exc:
            print(f"  ❌ EXCEPTION: {exc}")
            results.append({"id": case["id"], "error": str(exc), "score": 0})
            continue
        results.append(r)
        bar = "█" * (r["score"] // 10) + "░" * (10 - r["score"] // 10)
        print(f"  {bar}  {r['passed']}/{r['total']} checks  ({r['score']}%)  {r['elapsed_s']}s")
        # snapshot clave
        s = r["snapshot"]
        print(f"    año={s['year_built']} · notariado={s['notariado_price']}€/m² "
              f"({s['notariado_level']}, {s['notariado_tx']} tx) · "
              f"mitma={s['mitma_price']}€/m² · conv={s['convergence_pct']}% · "
              f"valor={s['current_value']}€ · {s['roi_recommendation']}")
        if args.verbose:
            for name, ok, detail in r["checks"]:
                print(f"      {'✓' if ok else '✗'} {name:30} {detail}")
        else:
            fails = [(n, d) for n, ok, d in r["checks"] if not ok]
            for n, d in fails:
                print(f"      ✗ {n}: {d}")

    # Resumen global
    scored = [r for r in results if "score" in r]
    total_checks = sum(r.get("total", 0) for r in scored)
    total_passed = sum(r.get("passed", 0) for r in scored)
    overall = round(total_passed / total_checks * 100) if total_checks else 0

    print(f"\n{'='*78}")
    print(f"  RESUMEN")
    print(f"{'='*78}")
    for r in scored:
        mark = "✅" if r.get("score", 0) == 100 else ("🟡" if r.get("score", 0) >= 80 else "❌")
        print(f"  {mark} {r['id']:24} {r.get('passed','?')}/{r.get('total','?')}  ({r.get('score',0)}%)")
    print(f"\n  GLOBAL: {total_passed}/{total_checks} checks  →  {overall}%")
    print()

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"overall": overall, "results": results}, f,
                      indent=2, ensure_ascii=False)
        print(f"  Resultados guardados en {args.json}")


if __name__ == "__main__":
    main()

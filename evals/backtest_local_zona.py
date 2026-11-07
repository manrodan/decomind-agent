"""Backtest LOCAL, paso 2 (venv del decomind-partner-api): sobre lo valorado por el motor (backtest_local_motor.py)
aplica el ajuste de zona de producción SIN y CON testigos de oferta y compara con el precio PEDIDO del anuncio.
No es precisión (lo pedido no es lo firmado): es cordura. Métrica: ratio valor/pedido por municipio y tipo
(mediana, p10, p90) y % fuera de [0,75, 1,00] (la valoración no debería superar lo pedido ni quedar a más de un 25 %).
El sujeto se excluye de sus propios testigos por calle y por precio+m² (precio_sujeto).

Uso: C:\\ProyectosVS\\decomind-partner-api\\.venv\\Scripts\\python.exe evals\\backtest_local_zona.py data/backtest_local/motor.json
     [--out data/backtest_local/zona.json] [--cache data/backtest_local/cache] [--limit N]
Caché: en disco (la búsqueda de zona y la de testigos se guardan por clave, como en el blob de producción), para que
repetir el backtest no vuelva a buscar. Reanudable por id.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, r"C:\ProyectosVS\decomind-partner-api")
_VALS = json.load(open(r"C:\ProyectosVS\decomind-partner-api\local.settings.json", encoding="utf-8"))["Values"]
os.environ.setdefault("GOOGLE_API_KEY", _VALS["GEMINI_API_KEY"])
os.environ["AzureWebJobsStorage"] = "UseDevelopmentStorage=true"  # el blob de producción no se toca

from shared import testigos as tg  # noqa: E402
from shared import zona_precio as zp  # noqa: E402


def _cache_en_disco(carpeta: str) -> None:
    """read_json/save_bytes de zona_precio y testigos → ficheros en `carpeta` (misma ruta que el blob)."""
    os.makedirs(carpeta, exist_ok=True)

    def read_json(path):
        p = os.path.join(carpeta, path.replace("/", os.sep))
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None

    def save_bytes(raw, path, content_type=None, sas_hours=None):
        p = os.path.join(carpeta, path.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(raw)
        return p

    for mod in (zp, tg):
        mod.read_json, mod.save_bytes = read_json, save_bytes


def _ratio(vr, pedido):
    v = ((vr or {}).get("valuation") or {}).get("current_value_eur")
    return round(v / pedido, 3) if v and pedido else None


def _resumen(filas: list[dict]) -> list[str]:
    out = ["| municipio | tipo | n | motor | zona | zona+testigos | fuera [0,75-1,0] motor → zona → testigos |",
           "|---|---|---|---|---|---|---|"]
    grupos: dict[tuple, list[dict]] = {}
    for f in filas:
        grupos.setdefault((f["listing"]["locality"], f["property_type"] or "?"), []).append(f)
        grupos.setdefault(("TODOS", "todos"), []).append(f)

    def stats(xs):
        xs = [x for x in xs if x]
        if not xs:
            return "—", "—"
        q = statistics.quantiles(xs, n=10) if len(xs) >= 3 else [min(xs), max(xs)]
        return f"{statistics.median(xs):.2f} ({q[0]:.2f}-{q[-1]:.2f})", f"{100 * sum(not 0.75 <= x <= 1.0 for x in xs) / len(xs):.0f} %"

    for (muni, tipo), fs in sorted(grupos.items(), key=lambda kv: (kv[0][0] == "TODOS", kv[0])):
        m, zz, tt = ([f[k] for f in fs] for k in ("r_motor", "r_zona", "r_testigos"))
        (sm, fm), (sz, fz), (st, ft) = stats(m), stats(zz), stats(tt)
        out.append(f"| {muni} | {tipo} | {len(fs)} | {sm} | {sz} | {st} | {fm} → {fz} → {ft} |")
    return out


def main() -> None:
    args = sys.argv[1:]
    src = args[0]
    out = args[args.index("--out") + 1] if "--out" in args else "data/backtest_local/zona.json"
    cache = args[args.index("--cache") + 1] if "--cache" in args else "data/backtest_local/cache"
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 10 ** 9
    _cache_en_disco(cache)
    motor = json.load(open(src, encoding="utf-8"))
    done = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else []
    hechos = {d["id"] for d in done}
    n = 0
    for m in motor:
        if m["id"] in hechos or n >= limit or not (m["motor"] or {}).get("found"):
            continue
        li, vr = m["listing"], m["motor"]
        kw = dict(municipio=li["locality"] or "", provincia=li["province"] or "", direccion=m["address"],
                  zona_anuncio=m["zona"] or "", property_type=m["property_type"] or "", precio_sujeto=li["price"])
        t0 = time.time()
        sin = zp.ajustar_por_zona(vr, testigos=False, **kw)
        con = zp.ajustar_por_zona(vr, testigos=True, **kw)
        v, za, t = con["valuation"], con["valuation"]["zone_adjustment"], con["valuation"].get("testigos") or {}
        fila = {"id": m["id"], "listing": li, "property_type": m["property_type"], "zona": m["zona"],
                "r_motor": _ratio(vr, li["price"]), "r_zona": _ratio(sin, li["price"]), "r_testigos": _ratio(con, li["price"]),
                "zona_motivo": za.get("motivo"), "zona_factor": za.get("factor"), "distrito": za.get("distrito"),
                "sin_zona": za.get("sin_zona"), "testigos_n": t.get("n"), "testigos_motivo": t.get("motivo"),
                "testigos_pct": t.get("pct"), "testigos_mediana": t.get("mediana_eur_m2"), "excluidos": t.get("excluidos"),
                "valor_motor": vr["valuation"]["current_value_eur"], "valor_zona": sin["valuation"]["current_value_eur"],
                "valor_testigos": v["current_value_eur"], "segundos": round(time.time() - t0),
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        print(f"{m['id']:>6} {li['locality'][:16]:<16} {m['property_type'] or '?':<8} pedido {li['price']:>8} · motor {fila['r_motor']} "
              f"· zona {fila['r_zona']} ({za.get('motivo')}) · testigos {fila['r_testigos']} (n={t.get('n')} {t.get('motivo')}) "
              f"en {fila['segundos']} s")
        done.append(fila)
        json.dump(done, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        n += 1
    print("\n".join(_resumen(done)))
    open(os.path.splitext(out)[0] + ".md", "w", encoding="utf-8").write("\n".join(_resumen(done)) + "\n")


if __name__ == "__main__":
    main()

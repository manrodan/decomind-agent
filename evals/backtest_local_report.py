"""Informe final del backtest local: motor / +zona / +zona+testigos. Excluye datos sucios (precio < 30k, ratio motor > 3 o < 0.2 = m² o precio mal capturados)."""
import json, os, statistics as st, sys, unicodedata
from collections import Counter, defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "bt_zona.json"), encoding="utf-8"))
def norm(s):
    s = unicodedata.normalize("NFKD", (s or "?").split("/")[0]).encode("ascii", "ignore").decode().strip().lower()
    return {"benicasim": "benicassim", "almazora": "almassora", "villarreal": "vila-real", "castellon": "castellon de la plana"}.get(s, s)
sucios = [r for r in rows if (r["listing"].get("price") or 0) < 30000 or not r.get("r_motor") or r["r_motor"] > 3 or r["r_motor"] < 0.2]
ok = [r for r in rows if r not in sucios]
def fuera(v): return 100 * sum(1 for q in v if q < 0.75 or q > 1.0) / len(v)
def arriba(v): return 100 * sum(1 for q in v if q > 1.0) / len(v)
def res(xs, k):
    v = [x[k] for x in xs if x.get(k)]
    if not v: return "-"
    q = st.quantiles(v, n=10) if len(v) >= 10 else None
    return f"{st.median(v):.2f}" + (f" ({q[0]:.2f}-{q[-1]:.2f})" if q else "")
out = []
out.append(f"# Backtest local · zona y testigos (2026-11-07)\n")
out.append(f"Muestra estratificada: {len(rows)} anuncios captados (≤15 por municipio, mitad casas). Excluidos {len(sucios)} con datos sucios (precio < 30 k€ o ratio motor fuera de [0,2, 3]): " + ", ".join(f"#{r['id']} {norm(r['listing'].get('locality'))} {r['listing'].get('price')}€/{r['listing'].get('m2')}m² r={r.get('r_motor')}" for r in sucios) + "\n")
out.append("Métrica: ratio valor/precio pedido. «Fuera» = fuera de [0,75, 1,0]; «>1» = valoración por encima de lo pedido. Mediana (p10-p90).\n")
out.append("## Global\n\n| capa | mediana (p10-p90) | fuera | >1 |\n|---|---|---|---|")
for k, n in (("r_motor", "motor"), ("r_zona", "+ zona"), ("r_testigos", "+ zona + testigos")):
    v = [x[k] for x in ok]
    out.append(f"| {n} | {res(ok, k)} | {fuera(v):.0f} % | {arriba(v):.0f} % |")
out.append(f"\nn = {len(ok)}. Motivos zona: {dict(Counter(x['zona_motivo'] for x in ok))}. Motivos testigos: {dict(Counter(x['testigos_motivo'] for x in ok))}.\n")
# por municipio (agregado) y por municipio+tipo
out.append("## Por municipio\n\n| municipio | n | motor | + zona | + testigos | fuera motor → zona → testigos |\n|---|---|---|---|---|---|")
por = defaultdict(list)
for x in ok: por[norm(x["listing"].get("locality"))].append(x)
for m, xs in sorted(por.items(), key=lambda kv: -len(kv[1])):
    f = " → ".join(f"{fuera([x[k] for x in xs]):.0f} %" for k in ("r_motor", "r_zona", "r_testigos"))
    out.append(f"| {m} | {len(xs)} | {res(xs,'r_motor')} | {res(xs,'r_zona')} | {res(xs,'r_testigos')} | {f} |")
out.append("\n## Por municipio y tipo (n ≥ 2)\n\n| municipio | tipo | n | motor | + zona | + testigos | fuera |\n|---|---|---|---|---|---|---|")
por2 = defaultdict(list)
for x in ok: por2[(norm(x["listing"].get("locality")), x.get("property_type") or "?")].append(x)
for (m, t), xs in sorted(por2.items()):
    if len(xs) < 2: continue
    f = " → ".join(f"{fuera([x[k] for x in xs]):.0f} %" for k in ("r_motor", "r_zona", "r_testigos"))
    out.append(f"| {m} | {t} | {len(xs)} | {res(xs,'r_motor')} | {res(xs,'r_zona')} | {res(xs,'r_testigos')} | {f} |")
# casas vs pisos
out.append("\n## Pisos frente a casas\n\n| tipo | n | motor | + zona | + testigos | fuera |\n|---|---|---|---|---|---|")
for nombre, xs in (("pisos/áticos", [x for x in ok if x.get("property_type") in ("piso", "atico")]), ("casas", [x for x in ok if x.get("property_type") not in ("piso", "atico")])):
    f = " → ".join(f"{fuera([x[k] for x in xs]):.0f} %" for k in ("r_motor", "r_zona", "r_testigos"))
    out.append(f"| {nombre} | {len(xs)} | {res(xs,'r_motor')} | {res(xs,'r_zona')} | {res(xs,'r_testigos')} | {f} |")
# efecto de los testigos cuando actúan
con = [x for x in ok if x.get("testigos_motivo") in ("ancla", "techo")]
out.append(f"\n## Cuando los testigos actúan (ancla/techo, n = {len(con)})\n")
mejora = sum(1 for x in con if abs(x["r_testigos"] - 0.875) < abs(x["r_zona"] - 0.875))
out.append(f"- Acercan al centro del margen (0,875) en {mejora} de {len(con)} casos ({100*mejora/len(con):.0f} %).")
out.append(f"- Pasan de fuera a dentro del margen: {sum(1 for x in con if (x['r_zona']<0.75 or x['r_zona']>1.0) and 0.75<=x['r_testigos']<=1.0)}; de dentro a fuera: {sum(1 for x in con if 0.75<=x['r_zona']<=1.0 and (x['r_testigos']<0.75 or x['r_testigos']>1.0))}.")
out.append(f"- Nº de anuncios por búsqueda: mediana {st.median([x['testigos_n'] for x in con])}, excluidos por ser el propio anuncio: {sum(x.get('excluidos') or 0 for x in ok)} en total.")
out.append(f"- Tiempo: mediana {st.median([x['segundos'] for x in ok]):.0f} s por anuncio (motor + zona×2 + testigos, sin caché en la primera búsqueda).")
# peores casos
out.append("\n## Peores casos tras testigos (|log ratio| mayor)\n\n| id | municipio | tipo | m² | pedido | motor | zona | testigos | motivo zona | motivo testigos | n |\n|---|---|---|---|---|---|---|---|---|---|---|")
import math
for x in sorted(ok, key=lambda x: -abs(math.log(x["r_testigos"])))[:15]:
    l = x["listing"]
    out.append(f"| {x['id']} | {norm(l.get('locality'))} | {x.get('property_type')} | {l.get('m2')} | {l.get('price')} | {x['r_motor']:.2f} | {x['r_zona']:.2f} | {x['r_testigos']:.2f} | {x.get('zona_motivo')} | {x.get('testigos_motivo')} | {x.get('testigos_n')} |")
# casos tope_pedido
tp = [x for x in ok if x.get("zona_motivo") == "tope_pedido"]
out.append(f"\n## Casos con tope «firmado < pedido» (n = {len(tp)})\n\n| id | municipio | tipo | pedido | motor | zona | testigos | testigos n |\n|---|---|---|---|---|---|---|---|")
for x in tp:
    l = x["listing"]
    out.append(f"| {x['id']} | {norm(l.get('locality'))} | {x.get('property_type')} | {l.get('price')} | {x['r_motor']:.2f} | {x['r_zona']:.2f} | {x['r_testigos']:.2f} | {x.get('testigos_n')} |")
txt = "\n".join(out)
open(os.path.join(HERE, "BASELINE_LOCAL.md"), "a", encoding="utf-8").write(txt) if "--append" in sys.argv else None
sys.stdout.reconfigure(encoding="utf-8"); print(txt)

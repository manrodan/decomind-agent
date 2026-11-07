"""Backtest LOCAL, paso 1 (venv de decomind-agent): valora a ciegas los anuncios captados por los agentes (tabla
`property` de Decomind: título, precio pedido, m², CP…) con el motor, como lo haría la app: dirección, tipo y zona
sacados del título igual que src/lib/listingAddress.js. El paso 2 (evals/backtest_local_zona.py, venv del partner-api)
añade el ajuste de zona y los testigos y compara con el precio pedido.

Uso: .venv\\Scripts\\python.exe -m evals.backtest_local_motor listings.json [--out data/backtest_local/motor.json]
     [--limit N]. Reanudable: los ids ya valorados en --out se saltan. Espacia 2 s (Nominatim).
Entrada: lista de {id, title, price, province, locality, postal_code, m2, rooms, baths, features_json, source}.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone

from valuation_api.engine import run_valuation

_STREET_RE = re.compile(r"^(calle|c/|avenida|avda|av\.?|avinguda|plaza|pza|pla[çc]a|carrer|camino|cam[ií]|paseo|passeig|"
                        r"ronda|traves[ií]a|partida|carretera|ctra|callej[oó]n|glorieta|pasaje|passatge|v[ií]a|cuesta)\b", re.I)
_HOUSE_RE = re.compile(r"^\s*(?:casa|chalet|villa|unifamiliar|adosad|pareado|mas[ií]a|cortijo|caser[ií]o|finca r[uú]stica)", re.I)
_FLAT_RE = re.compile(r"^\s*(?:piso|apartamento|estudio|d[uú]plex|loft|bajo|planta baja)\b", re.I)
_TIPO = (("adosad", "adosado"), ("paread", "pareado"), ("chalet", "chalet"), ("villa", "chalet"),
         ("unifamiliar", "unifamiliar"), ("casa", "casa"))


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").strip().lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def listing_parts(title: str) -> list[str]:
    """Espejo de listingParts (listingAddress.js): lo que va tras «en venta en …», en tramos."""
    a = (title or "").strip()
    m = re.search(r"(?:^|\s)en\s+(?:venta|alquiler)\s+en\s+(.+)$", a, re.I) or re.match(
        r"^\s*(?:piso|ático|atico|casa|chalet|adosado|pareado|dúplex|duplex|apartamento|estudio|loft|bajo|vivienda|finca|local)"
        r"\s+en\s+(.+)$", a, re.I)
    if m:
        a = m.group(1).strip()
    return [p.strip() for p in a.split(",") if p.strip()]


def clean_listing_address(title: str) -> str:
    parts = listing_parts(title)
    if len(parts) > 1 and re.match(r"^\d", parts[1]):
        return f"{parts[0]} {parts[1]}"
    return parts[0] if parts else (title or "").strip()


def listing_zone(title: str, locality: str = "") -> str:
    parts = listing_parts(title)
    munis = {_norm(x) for x in [locality, *str(locality or "").split("/")] if _norm(x)}
    is_muni = lambda p: any(_norm(x) in munis for x in p.split("/"))
    rest = [p for i, p in enumerate(parts) if not re.match(r"^\d", p) and not is_muni(p)
            and not (i == 0 and (_STREET_RE.search(p) or re.search(r"\d", p)))]
    return rest[0] if rest else ""


def listing_property_type(title: str, features: list[str]) -> str:
    """listingPropertyType afinado al tipo del motor (adosado/pareado/chalet/casa; atico; piso; '')."""
    heads = [str(s or "") for s in [title, *features]]
    for s in heads:
        if _HOUSE_RE.search(s):
            w = _norm(s)
            return next((t for k, t in _TIPO if k in w), "casa")
    if any(re.match(r"^\s*[aá]tico\b", s, re.I) for s in heads):
        return "atico"
    if any(_FLAT_RE.search(s) for s in heads):
        return "piso"
    return ""


def main() -> None:
    args = sys.argv[1:]
    src = args[0]
    out = args[args.index("--out") + 1] if "--out" in args else "data/backtest_local/motor.json"
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 10 ** 9
    listings = json.load(open(src, encoding="utf-8"))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    done = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else []
    hechos = {d["id"] for d in done}
    n = 0
    for li in listings:
        if li["id"] in hechos or n >= limit:
            continue
        if not (li.get("price") and li.get("m2")):
            continue
        feats = []
        try:
            feats = [str(x) for x in (json.loads(li.get("features_json") or "[]") or [])]
        except ValueError:
            pass
        title = li.get("title") or ""
        loc = (li.get("locality") or "").strip()
        address, zona, tipo = clean_listing_address(title), listing_zone(title, loc), listing_property_type(title, feats)
        t0 = time.time()
        try:
            vr = run_valuation(address=address, locality=loc, province=(li.get("province") or "").strip(),
                               postal_code=str(li.get("postal_code") or "").strip(), surface_m2=float(li["m2"]),
                               property_type=tipo, bedrooms=int(li.get("rooms") or 0), bathrooms=int(li.get("baths") or 0),
                               features=feats, include_renovation=False)
        except Exception as exc:  # noqa: BLE001 — el backtest sigue con el resto
            vr = {"found": False, "reason": f"error: {exc}"}
        v = vr.get("valuation") or {}
        print(f"{li['id']:>6} {loc[:18]:<18} {tipo or '?':<9} {float(li['m2']):>5.0f} m² pedido {int(li['price']):>8} → "
              f"motor {v.get('current_value_eur') or '-':>8} ({(vr.get('location') or {}).get('precision') or vr.get('reason')}) "
              f"zona «{zona}» en {time.time() - t0:.0f} s")
        done.append({"id": li["id"], "listing": {k: li.get(k) for k in ("title", "price", "province", "locality", "postal_code",
                                                                       "m2", "rooms", "baths", "source", "captured_via")},
                     "address": address, "zona": zona, "property_type": tipo, "features": feats, "motor": vr,
                     "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        json.dump(done, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        n += 1
        time.sleep(2)
    print(f"{len(done)} anuncios valorados en {out}")


if __name__ == "__main__":
    main()

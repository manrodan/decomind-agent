"""
Diagnóstico — para Benicàssim (u otra dirección), muestra:
  1. Qué devuelve Nominatim (todos los campos addr.*)
  2. Cómo lo normaliza nuestro _pick_real_province
  3. Qué claves tiene MITMA provincial (relevantes)
  4. Qué decide finalmente base_price_per_sqm

Uso:
    python -m scripts.debug_lookup
"""

from __future__ import annotations

import json

import httpx


ADDRESS_QUERY = "Calle Bayer 14, 12560, Benicàssim, Castellón, España"


def main() -> None:
    # 1) Nominatim raw
    print("=" * 70)
    print("1) Nominatim raw response")
    print("=" * 70)
    resp = httpx.get(
        "https://nominatim.openstreetmap.org/search",
        params={
            "q": ADDRESS_QUERY,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": 1,
            "countrycodes": "es",
            "accept-language": "es",
        },
        headers={"User-Agent": "decomind-agent-debug/0.1 (info@decomind.es)"},
        timeout=10,
    )
    data = resp.json()
    if not data:
        print("Sin resultado.")
        return
    hit = data[0]
    addr = hit.get("address") or {}
    print(f"display_name: {hit.get('display_name')}")
    print("\naddress fields:")
    for k, v in addr.items():
        print(f"  {k!r:25} = {v!r}")

    # 2) Pasar por nuestro picker
    print("\n" + "=" * 70)
    print("2) Nuestra extracción de provincia política")
    print("=" * 70)
    from mcp_servers.geocoding.server import _pick_real_province
    picked = _pick_real_province(addr)
    print(f"_pick_real_province → {picked!r}")
    print(f"municipality (city/town/village) → "
          f"{addr.get('city') or addr.get('town') or addr.get('village')!r}")

    # 3) Claves de MITMA provincial relevantes
    print("\n" + "=" * 70)
    print("3) Claves MITMA provincial (filtradas)")
    print("=" * 70)
    try:
        from mcp_servers.market_research.data_mitma import (
            PROVINCE_PRICE_PER_SQM_MITMA,
            MUNICIPALITY_PRICE_PER_SQM_MITMA,
        )
    except ImportError:
        print("data_mitma.py no existe — ejecuta `python -m scripts.parse_mitma` antes")
        return

    prov_keys = sorted(PROVINCE_PRICE_PER_SQM_MITMA.keys())
    print(f"Total provincias MITMA: {len(prov_keys)}")
    print("Filtradas (que contengan 'castell', 'valenc', 'comun', 'baleare', 'palma'):")
    for k in prov_keys:
        if any(x in k for x in ("castell", "valenc", "comun", "baleare", "palma")):
            print(f"  {k!r:35} = {PROVINCE_PRICE_PER_SQM_MITMA[k]} €/m²")

    print(f"\nTotal municipios MITMA: {len(MUNICIPALITY_PRICE_PER_SQM_MITMA)}")
    muni_with_bayer_zone = [
        k for k in MUNICIPALITY_PRICE_PER_SQM_MITMA
        if any(x in k for x in ("benicas", "benicàs", "castellon", "castello", "vinaroz", "vinaros"))
    ]
    print(f"Municipios MITMA cercanos a Benicàssim:")
    for k in sorted(muni_with_bayer_zone):
        print(f"  {k!r:35} = {MUNICIPALITY_PRICE_PER_SQM_MITMA[k]} €/m²")

    # 4) base_price_per_sqm con lo que devolvió Nominatim
    print("\n" + "=" * 70)
    print("4) base_price_per_sqm con datos de Nominatim")
    print("=" * 70)
    from mcp_servers.market_research.data import _norm, base_price_per_sqm

    muni_in = addr.get("city") or addr.get("town") or addr.get("village")
    prov_in = picked
    distr_in = addr.get("city_district") or addr.get("district")

    print(f"Inputs: municipality={muni_in!r}  province={prov_in!r}  district={distr_in!r}")
    print(f"Normalizados:")
    print(f"  _norm(municipality) = {_norm(muni_in)!r}")
    print(f"  _norm(province)     = {_norm(prov_in)!r}")
    print(f"  _norm(district)     = {_norm(distr_in)!r}")

    price = base_price_per_sqm(prov_in, distr_in, muni_in)
    print(f"\n→ base_price_per_sqm() = {price} €/m²")


if __name__ == "__main__":
    main()

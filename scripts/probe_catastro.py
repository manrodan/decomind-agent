"""
Probe de los servicios web libres del Catastro.

Prueba los 3 endpoints REST GET (datos no protegidos, gratis, sin auth) y
muestra el XML crudo, para diseñar el parser del MCP `catastro` sobre la
estructura real.

Uso:
    python -m scripts.probe_catastro
"""

from __future__ import annotations

import httpx

# Coordenadas reales de Calle Mayor 5, Madrid (las dio Nominatim antes).
LAT = 40.4163773
LON = -3.705515

BASE = "http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC"

# Catastro va mejor por HTTP. User-Agent normal para evitar bloqueos.
HEADERS = {"User-Agent": "decomind-agent/0.1 (info@decomind.es)"}


def _get(url: str, params: dict) -> str:
    with httpx.Client(timeout=15, headers=HEADERS, follow_redirects=True) as c:
        r = c.get(url, params=params)
        print(f"\n>>> GET {r.url}")
        print(f"    HTTP {r.status_code}")
        return r.text


def section(title: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


def main() -> None:
    # 1) Coordenadas → parcelas cercanas (robusto, devuelve distancia)
    section("1) Consulta_RCCOOR_Distancia — coordenadas → parcelas cercanas")
    rc_found = None
    try:
        xml = _get(
            f"{BASE}/OVCCoordenadas.asmx/Consulta_RCCOOR_Distancia",
            {"SRS": "EPSG:4326", "Coordenada_X": LON, "Coordenada_Y": LAT},
        )
        print(xml[:3000])
        # intentar extraer una RC (pc1+pc2) del XML
        import re
        m1 = re.search(r"<pc1>([^<]+)</pc1>", xml)
        m2 = re.search(r"<pc2>([^<]+)</pc2>", xml)
        if m1 and m2:
            rc_found = m1.group(1) + m2.group(1)
            print(f"\n[probe] RC extraída: {rc_found}")
    except Exception as exc:
        print(f"ERROR: {exc}")

    # 2) Por dirección directa — TODOS los params (incluso vacíos)
    section("2) Consulta_DNPLOC — dirección → datos inmueble (params completos)")
    try:
        xml = _get(
            f"{BASE}/OVCCallejero.asmx/Consulta_DNPLOC",
            {"Provincia": "MADRID", "Municipio": "MADRID",
             "Sigla": "CL", "Calle": "MAYOR", "Numero": "5",
             "Bloque": "", "Escalera": "", "Planta": "", "Puerta": ""},
        )
        print(xml[:4000])
        # extraer RC si DNPLOC la trae
        if not rc_found:
            import re
            m1 = re.search(r"<pc1>([^<]+)</pc1>", xml)
            m2 = re.search(r"<pc2>([^<]+)</pc2>", xml)
            if m1 and m2:
                rc_found = m1.group(1) + m2.group(1)
                print(f"\n[probe] RC extraída de DNPLOC: {rc_found}")
    except Exception as exc:
        print(f"ERROR: {exc}")

    # 3) DNPRC con RC de PARCELA (14) → lista inmuebles del edificio
    section("3) Consulta_DNPRC — RC parcela (14) → lista de inmuebles")
    rc = rc_found or "0244802VK4704C"
    print(f"(usando RC parcela = {rc})")
    try:
        xml = _get(
            f"{BASE}/OVCCallejero.asmx/Consulta_DNPRC",
            {"Provincia": "", "Municipio": "", "RC": rc},
        )
        print(xml[:1500])
    except Exception as exc:
        print(f"ERROR: {exc}")

    # 4) DNPRC con RC COMPLETA (20) → DETALLE del inmueble (sfc, ant, luso)
    section("4) Consulta_DNPRC — RC completa (20) → DETALLE inmueble")
    rc20 = (rc_found or "0244802VK4704C") + "0001AX"  # primer inmueble del edificio
    print(f"(usando RC completa = {rc20})")
    try:
        xml = _get(
            f"{BASE}/OVCCallejero.asmx/Consulta_DNPRC",
            {"Provincia": "", "Municipio": "", "RC": rc20},
        )
        # esta es la respuesta clave — mostrar entera
        print(xml[:6000])
    except Exception as exc:
        print(f"ERROR: {exc}")


if __name__ == "__main__":
    main()

"""
Probe del Valor de Referencia del Catastro — análisis de la página SECAccvr.

Determina si el valor aparece en el HTML sin identificación, o si hay muro
de login / postback ASPX / captcha.
"""

from __future__ import annotations

import re

import httpx

RC20 = "0244802VK4704C0001AX"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) decomind-agent/0.1"}


def main() -> None:
    url = "https://www1.sedecatastro.gob.es/Accesos/SECAccvr.aspx"
    with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as c:
        r = c.get(url, params={"refcat": RC20})
    html = r.text
    print(f"HTTP {r.status_code}  ·  {len(html)} chars  ·  final URL: {r.url}")

    low = html.lower()

    # 1) ¿Hay valores en euros en la página?
    euros = re.findall(r"[\d.]+,\d{2}\s*€|€\s*[\d.]+", html)
    print(f"\n[€] Importes detectados: {euros[:10]}")

    # 2) ¿Menciona 'valor de referencia' + número cerca?
    vr_ctx = re.findall(r".{0,60}valor de referencia.{0,80}", low)
    print(f"\n[VR] Contextos 'valor de referencia' ({len(vr_ctx)}):")
    for c_ in vr_ctx[:5]:
        print("    ...", c_.strip())

    # 3) ¿Muro de identificación?
    walls = {
        "cl@ve": "cl@ve" in low or "clave" in low,
        "certificado": "certificado" in low,
        "identif": "identif" in low,
        "acceda/inicie sesión": "inicie sesi" in low or "acceda" in low,
        "captcha": "captcha" in low or "recaptcha" in low,
        "no autorizado": "no autorizado" in low or "no tiene permiso" in low,
    }
    print("\n[muro] Señales de identificación requerida:")
    for k, v in walls.items():
        print(f"    {k:24} {'SÍ' if v else 'no'}")

    # 4) ¿Es postback ASPX (ViewState)?
    has_viewstate = "__viewstate" in low
    print(f"\n[aspx] Tiene __VIEWSTATE (postback): {'SÍ' if has_viewstate else 'no'}")

    # 5) Volcado de fragmentos con 'referencia' para inspección manual
    print("\n[dump] Fragmentos con posible dato de valor:")
    for m in re.finditer(r".{0,40}(referencia|importe|valor)[^<]{0,60}", low):
        frag = m.group(0).strip()
        if any(ch.isdigit() for ch in frag):
            print("    ...", frag[:120])


if __name__ == "__main__":
    main()

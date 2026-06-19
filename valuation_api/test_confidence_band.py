"""Self-check de la banda de confianza y de los códigos de segmento.

Sin red ni pytest:  python valuation_api/test_confidence_band.py
Cubre la lógica money-path nueva (banda centrada + ancho por convergencia).

La integración de notariado_price (sin segmento → 99/99 idéntico a hoy; segmento
con <15 ventas → fallback al agregado) se verificó EN VIVO contra el FeatureServer
del Notariado y no se mockea aquí (sería reimplementar ArcGIS para nada).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from valuation_api.engine import confidence_band  # noqa: E402
from mcp_servers.notariado.server import _CLASE_CODES, _TIPO_CODES  # noqa: E402


def test_central_siempre_dentro():
    # El central del motor = value_eur ≈ center_m2 * surface; debe caer dentro.
    iv, _ = confidence_band(2000, 90, 2000, 2100)
    central = 2000 * 90
    assert iv["low_eur"] <= central <= iv["high_eur"], (iv, central)


def test_convergente_mas_estrecha_que_divergente():
    _, conv = confidence_band(2000, 90, 2000, 2050)   # fuentes casi iguales
    _, div = confidence_band(2000, 90, 2000, 2600)    # fuentes lejanas
    assert conv < div, (conv, div)


def test_una_fuente_mas_ancha_que_acuerdo_perfecto():
    _, perfect = confidence_band(2000, 90, 2000, 2000)  # gap 0
    _, single = confidence_band(2000, 90, 2000, None)   # una sola fuente
    assert single > perfect, (single, perfect)


def test_techo_25pct():
    _, half = confidence_band(2000, 90, 1000, 9999)     # gap enorme
    assert half == 0.25, half


def test_sin_datos_devuelve_none():
    assert confidence_band(None, 90, 2000, 2000) == (None, None)
    assert confidence_band(2000, 0, 2000, 2000) == (None, None)


def test_codigos_de_segmento_confirmados():
    # Confirmados contra el FeatureServer vivo (probe_notariado.py 4c/4d).
    assert _CLASE_CODES == {"piso": 14, "unifamiliar": 15}
    assert _TIPO_CODES == {"nueva": 7, "usada": 9}


if __name__ == "__main__":
    checks = [v for k, v in sorted(globals().items())
              if k.startswith("test_") and callable(v)]
    for fn in checks:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(checks)} checks passed")

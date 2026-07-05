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
from mcp_servers.zona_valor.server import (  # noqa: E402
    _clamp_gradient, _parse_gfi, _PONENCIA_CACHE,
)


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


def test_gradiente_zona_amortiguado_y_acotado():
    # Gradiente de mercado = (ratio catastral)**0.5, acotado a ±30%.
    assert abs(_clamp_gradient(2440, 1958) - (2440 / 1958) ** 0.5) < 1e-9  # +25% bruto → +11.6%
    assert abs(_clamp_gradient(500, 2000) - 0.70) < 1e-9   # ratio 0.25 → sqrt 0.5 → suelo -30%
    assert abs(_clamp_gradient(1700, 881) - 1.30) < 1e-9   # Voramar/Benicàssim → tope +30%
    assert _clamp_gradient(2000, 2000) == 1.0              # ámbito uniforme
    assert _clamp_gradient(2440, 0) == 1.0                 # baseline 0 → guard
    assert _clamp_gradient(0, 2000) == 1.0                 # subject 0 → guard


def test_fallback_prefiere_residencial():
    # Caso hotel Voramar: el anillo ve U25 (508) y R17 (1700) → gana la R.
    from mcp_servers.zona_valor.server import _pick_fallback_zone
    hits = [{"code": "U25", "value": 508.0}, {"code": "R17", "value": 1700.0}]
    assert _pick_fallback_zone(hits)["code"] == "R17"
    # Solo zonas U → se usa la más frecuente / mayor valor de las que haya.
    hits_u = [{"code": "U25", "value": 508.0}, {"code": "U25", "value": 508.0},
              {"code": "U23", "value": 590.0}]
    assert _pick_fallback_zone(hits_u)["code"] == "U25"
    # Empate de frecuencia entre R → la de mayor valor (determinista).
    hits_tie = [{"code": "R24", "value": 1140.0}, {"code": "R17", "value": 1700.0}]
    assert _pick_fallback_zone(hits_tie)["code"] == "R17"


def test_ambito_median_solo_residencial():
    # Baseline = mediana de las zonas R (residencial); U/PU/PR fuera.
    from mcp_servers.zona_valor.server import _ambito_median
    assert _ambito_median({}) is None
    tabla = {"R17": 1700.0, "R24": 1140.0, "R29": 835.0,
             "PR23": 1205.0, "U48": 35.0, "U49": 28.0}
    assert _ambito_median(tabla) == 1140.0
    # Sin zonas R → respaldo con todas.
    assert _ambito_median({"U27": 443.0, "U29": 378.0}) == 410.5


def test_parse_gfi_zona_valor():
    # Parser del GetFeatureInfo sin red (sembramos la caché de ponencia).
    _PONENCIA_CACHE[("28", "900")] = {"R10E": 2440.0}
    z = _parse_gfi('<td>Municipio</td><td>Codigo</td><td>MADRID</td><td>R10E</td>'
                   ' window.open("ponencia.aspx?del=28&mun=900")')
    assert z == {"found": True, "code": "R10E", "value": 2440.0,
                 "del": "28", "mun": "900"}, z


def test_parse_gfi_sin_cobertura():
    # mun=0 = el WMS no encontró zona en ese punto → no-op.
    assert _parse_gfi('<td>Municipio</td> ponencia.aspx?del=41&mun=0') == {"found": False}


if __name__ == "__main__":
    checks = [v for k, v in sorted(globals().items())
              if k.startswith("test_") and callable(v)]
    for fn in checks:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(checks)} checks passed")

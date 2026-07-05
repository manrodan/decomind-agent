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


def test_surface_factor_relativo():
    # Con superficie media de zona: curva continua (media/superficie)^alpha.
    from mcp_servers.market_research.hedonic import surface_factor, _SURFACE_ALPHA
    assert abs(surface_factor(50, 94) - (94 / 50) ** _SURFACE_ALPHA) < 1e-9  # ≈ +29%
    assert surface_factor(50, 94) < 1.35                # bajo el tope (calibrado Fotocasa 1D +30%)
    assert surface_factor(94, 94) == 1.0                # en la media → neutro
    assert surface_factor(20, 200) == 1.35              # tope superior
    assert surface_factor(400, 90) == 0.80              # suelo
    assert surface_factor(50, None) == 1.10             # sin media → banda absoluta
    assert surface_factor(50, 0) == 1.10


def test_blend_shrinkage_notariado():
    from mcp_servers.notariado.server import _blend_price
    cp = {"precio_m2": 1000.0, "total": 30, "superficie_media": 80.0}
    muni = {"precio_m2": 1400.0, "total": 900}
    attrs, w = _blend_price(cp, muni)
    assert w == 0.5                                     # n/(n+30) con n=30
    assert attrs["precio_m2"] == 1200.0                 # mezcla 50/50
    assert attrs["superficie_media"] == 80.0            # composición local se conserva
    assert _blend_price(cp, None) == (cp, 1.0)          # sin municipio → CP puro
    assert _blend_price(None, muni)[1] == 0.0           # sin CP → municipio puro
    assert _blend_price(None, None) is None


def test_ipv_pick_trend():
    from mcp_servers.market_research.data_ipv import pick_trend, ccaa_for_province
    items = [
        {"Nombre": "Nacional. General. Variación anual. ",
         "Data": [{"Valor": 12.9, "Anyo": 2025, "FK_Periodo": 22}]},
        {"Nombre": "Comunitat Valenciana. Vivienda segunda mano. Variación anual. ",
         "Data": [{"Valor": 14.0, "Anyo": 2025, "FK_Periodo": 22}]},
    ]
    t = pick_trend(items, "Comunitat Valenciana", "usada")
    assert t["annual_pct"] == 14.0 and t["scope"] == "Comunitat Valenciana"
    # CCAA sin serie pedida → cae a Nacional (General).
    t2 = pick_trend(items, "Aragón", "")
    assert t2["annual_pct"] == 12.9 and t2["scope"] == "Nacional"
    assert ccaa_for_province("Castellón/Castelló") == "Comunitat Valenciana"
    assert ccaa_for_province("Madrid") == "Madrid, Comunidad de"
    assert ccaa_for_province("Vizcaya") == "País Vasco"


def test_info_dispersion():
    from valuation_api.engine import info_dispersion
    assert info_dispersion() == 0.08                                   # sin info extra
    assert info_dispersion(num_transactions=449) == 0.06               # muestra amplia
    assert info_dispersion(num_transactions=449,
                           location_signals_agree=True) == 0.05        # + señales de acuerdo
    assert info_dispersion(num_transactions=449, location_signals_agree=True,
                           unknown_count=4) == 0.06                    # 2 desconocidos extra
    assert info_dispersion(num_transactions=12,
                           location_signals_agree=False,
                           unknown_count=8) == 0.12                    # techo
    assert info_dispersion(num_transactions=100000,
                           location_signals_agree=True) == 0.05        # suelo


def test_antiquity_relativa():
    from mcp_servers.market_research.hedonic import antiquity_factor
    assert abs(antiquity_factor(2000, 1974) - 1.078) < 1e-9   # +26 años vs parque → +7.8%
    assert antiquity_factor(1950, 1975) == 0.925              # -25 años → -7.5%
    assert antiquity_factor(2026, 1950) == 1.10               # cota superior
    assert antiquity_factor(1900, 2005) == 0.90               # cota inferior
    assert antiquity_factor(2000, 2000) == 1.0                # en el parque típico → neutro
    assert antiquity_factor(2000, None) == 1.00               # sin zona → banda absoluta (26 años)
    assert antiquity_factor(None, 1974) == 1.0                # sin año → neutro


def test_stock_age_fallback():
    import mcp_servers.seccion_censal.server as scs
    old = scs._stock_cache
    scs._stock_cache = {"secciones": {"1204006004": 1974}, "municipios": {"12040": 1976}}
    try:
        assert scs.stock_age_year("1204006004", "12040") == 1974   # sección directa
        assert scs.stock_age_year("9999999999", "12040") == 1976   # fallback municipio
        assert scs.stock_age_year("9999999999", "99999") is None   # sin dato
        assert scs.stock_age_year(None, None) is None
    finally:
        scs._stock_cache = old


def test_combine_gradients():
    from valuation_api.engine import _combine_gradients
    assert _combine_gradients([None, None]) == 1.0
    assert _combine_gradients([1.2, None]) == 1.2          # una sola señal → tal cual
    assert _combine_gradients([0.9154, 1.10]) == 1.0035    # discrepantes → se moderan
    assert _combine_gradients([1.30, 1.25]) == 1.2748      # ambas altas → media geom.
    assert _combine_gradients([2.0, 2.0]) == 1.30          # cota superior ±30%
    assert _combine_gradients([0.4]) == 0.70               # cota inferior


def test_seccion_signal_puro():
    from mcp_servers.seccion_censal.server import _signal_from_data, _gradient_from_ratios
    data = {"secciones": {"1204001001": [8.0, 35000]},
            "municipios": {"12040": [6.4, 28000]}}
    sig = _signal_from_data(data, "1204001001", "12040")
    assert sig["ratios"] == [1.25, 1.25]
    g = _gradient_from_ratios(sig["ratios"])
    assert abs(g - 1.25 ** 0.7) < 1e-9                     # ≈ +16.9%
    assert _signal_from_data(data, "9999999999", "12040") is None
    assert _signal_from_data({}, "x", "y") is None
    # Sección con solo renta (sin alquiler) → un ratio, funciona igual.
    data2 = {"secciones": {"A": [None, 42000]}, "municipios": {"M": [6.0, 28000]}}
    assert _signal_from_data(data2, "A", "M")["ratios"] == [1.5]
    assert _gradient_from_ratios([]) == 1.0


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

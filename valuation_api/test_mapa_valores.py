"""Self-check del gradiente del mapa de valores de referencia (sin red).

    python valuation_api/test_mapa_valores.py

httpx mockeado con un municipio de 3 ámbitos: A (pisos 2.000 €/m², 100 viv.),
B (pisos 1.000, 100 viv.) y C (unifamiliar 1.500, 50 viv.). Base de pisos =
media ponderada 1.500 → en A el gradiente es (2000/1500)**0.5 = 1,1547.
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

import mcp_servers.catastro.server as cat  # noqa: E402
import mcp_servers.zona_valor.server as zv  # noqa: E402

_RealClient = httpx.Client


def _sq(lon0, lat0, d=0.01):
    return [[lon0, lat0], [lon0 + d, lat0], [lon0 + d, lat0 + d], [lon0, lat0 + d], [lon0, lat0]]


def _feat(cod, ring, tipologia, m2, n, tip2=None, m2_2=0):
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"id_delegacion": "12", "id_municipio": "28", "cod_zona": cod, "ejercicio": 2026,
                           "num_inmuebles_uso_v": n,
                           "Ptipo1": {"tipologia": tipologia, "val_tipo_m2": m2},
                           "Ptipo2": {"tipologia": tip2, "val_tipo_m2": m2_2}}}


_A = _sq(0.00, 40.00)   # pisos 2000
_B = _sq(0.02, 40.00)   # pisos 1000
_C = _sq(0.04, 40.00)   # unifamiliar 1500
GEO = {"type": "FeatureCollection", "features": [
    _feat("A", _A, "Vivienda colectiva", 2000, 100),
    _feat("B", _B, "Vivienda colectiva", 1000, 100),
    _feat("C", _C, "Vivienda unifamiliar aislada/pareada", 1500, 50),
    _feat("V", _sq(0.06, 40.00), None, 0, 0),  # ámbito sin dato (como los grises del mapa)
]}
VACIO = {"type": "FeatureCollection", "features": []}


@contextmanager
def _catastro(handler):
    def client(**kw):
        return _RealClient(transport=httpx.MockTransport(handler), **kw)
    with mock.patch.object(httpx, "Client", client), mock.patch.object(cat, "RETRY_PAUSE_S", 0):
        zv._MAPA_CACHE.clear()
        yield
        zv._MAPA_CACHE.clear()


def _sirve(geo_por_anyo):
    calls = []

    def handler(req):
        calls.append(req)
        anyo = int(req.url.params["anyoZV"])
        body = geo_por_anyo.get(anyo, VACIO)
        return httpx.Response(200, text=body if isinstance(body, str) else json.dumps(body))
    return handler, calls


def test_gradiente_pisos_en_zona_cara():
    handler, calls = _sirve({2027: GEO})
    with _catastro(handler):
        g = zv.mapa_valores_gradient(40.005, 0.005, "piso")
    assert g["found"] and g["zone_code"] == "MVA" and g["neighborhood_mean"] == 1500.0, g
    assert abs(g["gradient"] - 1.1547) < 1e-3, g
    assert g["anyo"] == 2027 and len(calls) == 1, (g, len(calls))


def test_cae_al_anyo_actual_si_el_siguiente_viene_vacio_o_html():
    handler, calls = _sirve({2027: "<!DOCTYPE html><html>error</html>", 2026: GEO})
    with _catastro(handler):
        g = zv.mapa_valores_gradient(40.005, 0.025, "piso")
    assert g["found"] and g["zone_code"] == "MVB" and abs(g["gradient"] - (1000 / 1500) ** 0.5) < 1e-3, g
    assert g["anyo"] == 2026 and len(calls) == 2, (g, len(calls))


def test_clase_distinta_no_ajusta_y_lo_dice():
    handler, _ = _sirve({2027: GEO})
    with _catastro(handler):
        g = zv.mapa_valores_gradient(40.005, 0.005, "unifamiliar")  # chalet en zona de pisos
        u = zv.mapa_valores_gradient(40.005, 0.045, "unifamiliar")  # en C: única zona unifamiliar → base = ella misma
    assert not g["found"] and g["reason"] == "clase", g
    assert u["found"] and u["gradient"] == 1.0, u


def test_sin_clase_o_sin_ambito_no_ajusta():
    handler, calls = _sirve({2027: GEO})
    with _catastro(handler):
        assert not zv.mapa_valores_gradient(40.005, 0.005, "")["found"]
        assert len(calls) == 0  # sin clase ni se pide
        g = zv.mapa_valores_gradient(40.005, 0.065, "piso")  # ámbito sin dato
    assert not g["found"] and g["reason"] == "sin_ambito", g


def test_punto_fuera_del_poligono_usa_el_anillo_sin_red():
    handler, calls = _sirve({2027: GEO})
    with _catastro(handler):
        g = zv.mapa_valores_gradient(40.005, -0.0005, "piso")  # 40 m al oeste de A (playa)
    assert g["found"] and g["zone_code"] == "MVA", g
    assert len(calls) == 1, len(calls)


def test_cache_por_municipio_y_error_de_red():
    handler, calls = _sirve({2027: GEO})
    with _catastro(handler):
        zv.mapa_valores_gradient(40.005, 0.005, "piso")
        zv.mapa_valores_gradient(40.002, 0.022, "piso")
        assert len(calls) == 1, len(calls)  # segundo punto del mismo municipio: sin red

    def caido(req):
        raise httpx.ConnectError("boom", request=req)
    with _catastro(caido):
        g = zv.mapa_valores_gradient(40.005, 0.005, "piso")
    assert g == {"found": False, "gradient": 1.0, "error": True}, g


def test_baseline_ponderada():
    zonas = [{"n": 100, "productos": [{"clase": "piso", "m2": 2000.0, "n": 100}]},
             {"n": 300, "productos": [{"clase": "piso", "m2": 1000.0, "n": 300}]},
             {"n": 50, "productos": [{"clase": "unifamiliar", "m2": 9999.0, "n": 50}]}]
    assert zv._mapa_baseline(zonas, "piso") == 1250.0
    assert zv._mapa_baseline(zonas, "unifamiliar") == 9999.0
    assert zv._mapa_baseline(zonas, "otra") is None


def test_isla_dentro_de_un_hueco_no_hereda_el_envolvente():
    isla = _sq(0.003, 40.003, 0.002)
    envolvente = _feat("E", _A, "Vivienda colectiva", 1000, 100)
    envolvente["geometry"]["coordinates"].append(isla)  # hueco
    geo = {"type": "FeatureCollection", "features": [envolvente, _feat("I", isla, "Vivienda colectiva", 3000, 100)]}
    handler, _ = _sirve({2027: geo})
    with _catastro(handler):
        g = zv.mapa_valores_gradient(40.004, 0.004, "piso")   # en la isla
        e = zv.mapa_valores_gradient(40.008, 0.008, "piso")   # en el envolvente
    assert g["zone_code"] == "MVI" and e["zone_code"] == "MVE", (g, e)


def test_punto_sin_ambito_no_vuelve_a_descargar_y_html_es_error():
    handler, calls = _sirve({2027: GEO})
    with _catastro(handler):
        assert zv.mapa_valores_gradient(40.005, 0.005, "piso")["found"]
        a = zv.mapa_valores_gradient(40.5, 0.5, "piso")  # lejos de todo: mar/foral
        b = zv.mapa_valores_gradient(40.5, 0.5, "piso")
    # el mock devuelve el mismo municipio para el punto lejano: 1 descarga y luego nada (miss cacheado)
    assert not a["found"] and not b["found"] and len(calls) == 2, (a, b, len(calls))

    solo_html, calls = _sirve({2027: "<html>", 2026: "<html>"})
    with _catastro(solo_html):
        g = zv.mapa_valores_gradient(40.005, 0.005, "piso")
    assert g.get("error") and len(calls) == 2, (g, len(calls))


def test_municipio_grande_tope_corto():
    feats = [_feat(f"Z{i}", _sq(0.0 + 0.011 * i, 40.0), "Vivienda colectiva", 1000, 10) for i in range(120)]
    feats[0]["properties"]["Ptipo1"]["val_tipo_m2"] = 5000  # zona 0 muy por encima
    handler, _ = _sirve({2027: {"type": "FeatureCollection", "features": feats}})
    with _catastro(handler):
        g = zv.mapa_valores_gradient(40.005, 0.005, "piso")
    assert g["found"] and g["gradient"] == 1.15 and g["bound"] == 0.15, g


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except AssertionError as exc:
                fails += 1
                print("FAIL", name, exc)
    sys.exit(1 if fails else 0)

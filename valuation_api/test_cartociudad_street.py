"""Self-check de CartoCiudad para calles SIN número (sin red).

    python valuation_api/test_cartociudad_street.py

`candidates` devuelve la calle («callejero») con lat/lng 0; `find` trae el trazado.
El motor debe quedarse con el centro de la calle (precisión calle → ajuste de zona)
y no afirmar un CP cuando la calle cruza varios.
"""
from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mcp_servers.geocoding.server as geo  # noqa: E402

CAND = {"id": "120280000667", "type": "callejero", "muni": "Benicàssim/Benicasim", "postalCode": "12560",
        "address": "CALLE JOSE BELLIDO MOR, Urbanització El Quadro de Santiago", "lat": 0.0, "lng": 0.0}
FIND = {"id": "120280000667", "type": "callejero", "lat": 0.0, "lng": 0.0,
        "geom": "MULTILINESTRING((0.0360 40.0270,0.0370 40.0272),(0.0380 40.0268,0.0366 40.0270))"}


class _Resp:
    def __init__(self, data):
        self._d, self.text = data, "x"

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


def _http(candidates, find=None, calls=None):
    def get(url, params=None, **kw):
        (calls if calls is not None else []).append(url.rsplit("/", 1)[-1])
        return _Resp(candidates if url.endswith("candidates") else (find or {}))
    return get


def test_calle_sin_numero_usa_el_centro_del_trazado():
    calls = []
    with mock.patch.object(geo.httpx, "get", _http([CAND], FIND, calls)):
        g = geo.cartociudad_street("Calle Jose Bellido Mor", "Benicasim", "12560")
    assert g and g["found"] and g["house_number"] is None, g
    assert abs(float(g["lat"]) - 40.0270) < 1e-3 and abs(float(g["lon"]) - 0.0369) < 1e-3, g
    assert g["postcode"] == "12560" and calls == ["candidates", "find"], (g, calls)


def test_sin_trazado_no_inventa_coordenadas():
    with mock.patch.object(geo.httpx, "get", _http([CAND], {"geom": None})):
        assert geo.cartociudad_street("Calle Jose Bellido Mor", "Benicasim", "12560") is None


def test_calle_de_varios_cp_solo_afirma_el_pedido():
    c = {**CAND, "postalCode": "12002 12005", "muni": "Castelló de la Plana/Castellón de la Plana"}
    with mock.patch.object(geo.httpx, "get", _http([c], FIND)):
        con = geo.cartociudad_street("Calle Sagasta", "Castellón de la Plana", "12005")
        sin = geo.cartociudad_street("Calle Sagasta", "Castellón de la Plana", "")
    assert con["postcode"] == "12005" and sin["postcode"] is None, (con, sin)


def test_portal_con_coordenadas_sigue_igual():
    portal = {**CAND, "type": "portal", "portalNumber": 22, "lat": 40.0271, "lng": 0.0367}
    calls = []
    with mock.patch.object(geo.httpx, "get", _http([portal], FIND, calls)):
        g = geo.cartociudad_street("Calle Jose Bellido Mor 22", "Benicasim", "12560")
    assert g["house_number"] == "22" and g["lat"] == "40.0271" and calls == ["candidates"], (g, calls)


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

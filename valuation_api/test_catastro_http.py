"""Self-check del acceso al Catastro: 1 reintento ante cortes + anillo en serie.

Sin red ni pytest:  python valuation_api/test_catastro_http.py
httpx mockeado (MockTransport). Se pone en rojo si alguien quita el reintento,
reintenta timeouts (doblarían el peor caso de latencia) o vuelve a lanzar el
anillo de zona de valor en paralelo: desde Cloud Run el Catastro solo admite
~2 conexiones simultáneas por IP (logs sep-2026: 87 % de fallos con 8 hilos).
"""
from __future__ import annotations

import os
import sys
import threading
import time
from contextlib import contextmanager
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

import mcp_servers.catastro.server as cat  # noqa: E402
import mcp_servers.zona_valor.server as zv  # noqa: E402

_RealClient = httpx.Client
_LAT, _LON = 39.9387, -0.1069  # Vila-real (el caso del incidente)


@contextmanager
def _catastro(handler):
    """Todo httpx.Client → MockTransport(handler), y sin la pausa del reintento."""
    def client(**kw):
        return _RealClient(transport=httpx.MockTransport(handler), **kw)
    with mock.patch.object(httpx, "Client", client), \
            mock.patch.object(cat, "RETRY_PAUSE_S", 0):
        yield


def _drop(req):
    raise httpx.RemoteProtocolError(
        "Server disconnected without sending a response.", request=req)


def test_reintenta_una_vez_ante_corte():
    calls = []

    def handler(req):
        calls.append(req)
        return _drop(req) if len(calls) == 1 else httpx.Response(200, text="<ok/>")
    with _catastro(handler):
        assert cat.catastro_get("http://ovc/x", {}).text == "<ok/>"
    assert len(calls) == 2, len(calls)


def test_se_rinde_tras_el_reintento_y_no_reintenta_timeouts():
    for exc, expected in ((httpx.ReadError, 2), (httpx.ConnectError, 2),
                          (httpx.ReadTimeout, 1), (httpx.ConnectTimeout, 1)):
        calls = []

        def handler(req, exc=exc):
            calls.append(req)
            raise exc("boom", request=req)
        with _catastro(handler):
            assert cat._get_xml("OVCCoordenadas.asmx/Consulta_RCCOOR_Distancia", {}) is None
        assert len(calls) == expected, (exc.__name__, len(calls))


def test_lookup_no_insiste_inmueble_a_inmueble_si_el_catastro_corta():
    # Parcela OK con 3 inmuebles, pero el detalle se corta → 1 inmueble + su
    # reintento y se para (antes: los 8, y con reintento 16 → timeout de 60 s).
    calls = []

    def handler(req):
        calls.append(req)
        if "RCCOOR" in req.url.path:
            return httpx.Response(200, text="<r><pcd><pc><pc1>7352717</pc1>"
                                  "<pc2>YK4275S</pc2></pc><dis>3</dis></pcd></r>")
        if len(req.url.params["RC"]) == 14:
            rcs = "".join(f"<rcdnp><rc><pc1>7352717</pc1><pc2>YK4275S</pc2><car>000{i}"
                          "</car><cc1>A</cc1><cc2>B</cc2></rc></rcdnp>" for i in (1, 2, 3))
            return httpx.Response(200, text=f"<r><lrcdnp>{rcs}</lrcdnp></r>")
        return _drop(req)
    with _catastro(handler):
        r = cat.catastro_lookup(_LAT, _LON)
    assert r["found"] and r["units_count"] == 3 and r["year_built"] is None, r
    assert len(calls) == 4, len(calls)  # RCCOOR + parcela + 1 inmueble ×2


def test_anillo_en_serie():
    # Píxel sin zona (mun=0) en todos los puntos → sujeto + los 3 anillos enteros.
    state = {"inflight": 0, "peak": 0, "n": 0}
    lock = threading.Lock()

    def handler(req):
        with lock:
            state["inflight"] += 1
            state["n"] += 1
            state["peak"] = max(state["peak"], state["inflight"])
        time.sleep(0.01)
        with lock:
            state["inflight"] -= 1
        return httpx.Response(200, text="<td>X</td> ponencia.aspx?del=12&mun=0")
    with _catastro(handler):
        assert zv.zona_valor_gradient(_LAT, _LON) == {"found": False, "gradient": 1.0}
    assert state["n"] == 1 + 8 * len(zv._FALLBACK_RADII_M), state
    assert state["peak"] == 1, state  # nunca >1 conexión simultánea al Catastro

    # Catastro lento: el tope de tiempo corta el muestreo (en serie no escala).
    state["n"] = 0
    with _catastro(handler), mock.patch.object(zv, "_FALLBACK_BUDGET_S", 0.03):
        assert zv.zona_valor_gradient(_LAT, _LON)["found"] is False
    assert 2 <= state["n"] <= 6, state


def test_catastro_caido_no_lanza_el_anillo_ni_cachea_la_ponencia():
    calls = []

    def handler(req):
        calls.append(req)
        return _drop(req)
    with _catastro(handler):
        assert zv.zona_valor_gradient(_LAT, _LON)["found"] is False
    assert len(calls) == 2, len(calls)  # sujeto + su reintento; sin anillo

    # GFI con zona pero la ponencia se corta → error, y NO queda cacheada vacía.
    zv._PONENCIA_CACHE.pop(("12", "135"), None)

    def handler2(req):
        if "ponencia.aspx" in req.url.path:
            return _drop(req)
        return httpx.Response(200, text="<td>R12</td> ponencia.aspx?del=12&mun=135")
    with _catastro(handler2):
        assert zv.zona_valor_lookup(_LAT, _LON) == {"found": False, "error": True}
    assert ("12", "135") not in zv._PONENCIA_CACHE


if __name__ == "__main__":
    checks = [v for k, v in sorted(globals().items())
              if k.startswith("test_") and callable(v)]
    for fn in checks:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(checks)} checks passed")

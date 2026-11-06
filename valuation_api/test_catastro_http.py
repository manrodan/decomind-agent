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
        # error=True: el motor lo marca como fuente caída, no como «sin cobertura».
        assert zv.zona_valor_gradient(_LAT, _LON) == {"found": False, "gradient": 1.0, "error": True}
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


_CPMRC_OK = ("<consulta_coordenadas xmlns=\"http://www.catastro.meh.es/\"><control><cucoor>1</cucoor>"
             "<cuerr>0</cuerr></control><coordenadas><coord><pc><pc1>0782001</pc1><pc2>BE5308S</pc2></pc>"
             "<geo><xcen>0.0771050567509312</xcen><ycen>40.0554124346474</ycen><srs>EPSG:4326</srs></geo>"
             "<ldt>CL BISBE SERRA 5 BENICASIM / BENICASSIM (CASTELLÓN)</ldt></coord></coordenadas>"
             "</consulta_coordenadas>")
_CPMRC_ERR = ("<consulta_coordenadas xmlns=\"http://www.catastro.meh.es/\"><control><cuerr>1</cuerr></control>"
              "<lerr><err><cod>1</cod><des>LA REFERENCIA CATASTRAL NO EXISTE</des></err></lerr>"
              "</consulta_coordenadas>")


def test_referencia_catastral_da_el_punto():
    # Bisbe Serra 5 (Benicàssim): la de 20 caracteres vale (se usan los 14 de la parcela).
    seen = []

    def ok(req):
        seen.append(req.url.params.get("RC"))
        return httpx.Response(200, text=_CPMRC_OK)
    with _catastro(ok):
        r = cat.catastro_rc_point("0782001 BE5308S 0012 XY")
    assert r["found"] and round(r["lat"], 4) == 40.0554 and round(r["lon"], 4) == 0.0771, r
    assert seen == ["0782001BE5308S"], seen
    with _catastro(lambda req: httpx.Response(200, text=_CPMRC_ERR)):
        assert cat.catastro_rc_point("0782001XX9999Z") == {"found": False}   # mal copiada
    with _catastro(_drop):
        assert cat.catastro_rc_point("0782001BE5308S") == {"found": False, "error": True}  # caído
    assert cat.catastro_rc_point("123") == {"found": False}  # demasiado corta: ni se consulta


if __name__ == "__main__":
    checks = [v for k, v in sorted(globals().items())
              if k.startswith("test_") and callable(v)]
    for fn in checks:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(checks)} checks passed")

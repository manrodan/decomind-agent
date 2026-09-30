"""Self-check: el Catastro (año oficial) solo se consulta con el punto del PORTAL.

Sin red ni pytest:  python valuation_api/test_portal_point.py
Caso real (2026-09-30): "Calle Josep Ramón Batalla 60, Vila-real". OSM no tiene
el portal → Nominatim da el centro de la calle, y el Catastro devolvía la parcela
(y el año) de otro edificio. El nº 60 ni siquiera existe en el Catastro, y
CartoCiudad responde con el 61 (otra acera): tampoco vale.
"""
from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mcp_servers.geocoding.server as geo_srv  # noqa: E402
from valuation_api import engine  # noqa: E402

GEO_ROAD = {"found": True, "lat": "39.9388", "lon": "-0.1068", "municipality": "Vila-real"}
GEO_PORTAL = {**GEO_ROAD, "house_number": "60"}


def _carto(portal_number):
    resp = mock.Mock(text="{}", status_code=200)
    resp.raise_for_status = lambda: None
    resp.json.return_value = {"type": "portal", "portalNumber": portal_number,
                              "lat": 39.937, "lng": -0.106, "refCatastral": "7349908YK4274N"}
    return resp


def main() -> None:
    addr = "Calle Josep Ramón Batalla 60"

    # 1. Nominatim trae el número → su punto vale y no se llama a CartoCiudad.
    with mock.patch.object(engine, "cartociudad_portal") as carto:
        assert engine._portal_point(GEO_PORTAL, addr, "") == ((39.9388, -0.1068), 60)
        carto.assert_not_called()

    # 2. Centro de calle + CartoCiudad con ESE número → punto de CartoCiudad.
    with mock.patch.object(engine, "cartociudad_portal",
                           return_value={"lat": 39.9371, "lon": -0.1061}):
        assert engine._portal_point(GEO_ROAD, addr, "") == ((39.9371, -0.1061), 60)

    # 3. Centro de calle y sin portal → sin punto (no se consulta el Catastro).
    with mock.patch.object(engine, "cartociudad_portal", return_value=None):
        assert engine._portal_point(GEO_ROAD, addr, "") == (None, 60)

    # 4. Sin número en la dirección → sin punto y sin llamada.
    with mock.patch.object(engine, "cartociudad_portal") as carto:
        assert engine._portal_point(GEO_ROAD, "Calle Josep Ramón Batalla", "") == (None, None)
        carto.assert_not_called()

    # 5. CartoCiudad devuelve el portal más cercano en número (61 al pedir 60):
    #    se descarta; solo vale el número exacto.
    with mock.patch.object(geo_srv.httpx, "get", return_value=_carto(61)):
        assert geo_srv.cartociudad_portal(addr, "Vila-real", 60) is None
    with mock.patch.object(geo_srv.httpx, "get", return_value=_carto(60)):
        assert geo_srv.cartociudad_portal(addr, "Vila-real", 60)["lat"] == 39.937

    print("portal point OK (5/5)")


if __name__ == "__main__":
    main()

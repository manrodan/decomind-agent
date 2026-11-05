"""Self-check: la consulta a Nominatim no repite partes y se queda con el municipio pedido.

Sin red ni pytest:  python valuation_api/test_geocode_query.py
Caso real (2026-11-05, Informe de Captación): "Oliva pueblo", localidad Oliva.
El intento a nivel zona preguntaba "Oliva, Oliva, España" y Nominatim daba el
Parc Natural de la Marjal Pego-Oliva (Pego, Alicante): se valoraba con el
Notariado de Pego y el MIVAU de la provincia de Alicante.
"""
from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mcp_servers.geocoding.server as geo  # noqa: E402

PARK = {"lat": "38.89", "lon": "-0.07", "display_name": "Parc Natural de la Marjal Pego-Oliva",
        "address": {"town": "Pego", "province": "Alicante"}}
TOWN = {"lat": "38.92", "lon": "-0.12", "display_name": "Oliva, La Safor, Valencia",
        "address": {"town": "Oliva", "province": "Valencia", "postcode": "46780"}}


def _client(hits, seen):
    resp = mock.Mock()
    resp.raise_for_status = lambda: None
    resp.json.return_value = hits
    cli = mock.MagicMock()
    cli.__enter__.return_value.get.side_effect = lambda url, params, headers: seen.append(params["q"]) or resp
    return cli


def main() -> None:
    # 1. Zona = localidad: "Oliva" una sola vez en la consulta.
    seen: list[str] = []
    with mock.patch.object(geo.httpx, "Client", return_value=_client([TOWN], seen)):
        geo.geocode_address("Oliva", locality="Oliva", province="Valencia")
    assert seen == ["Oliva, Valencia, España"], seen

    # 2. Primer resultado en otro municipio → el del municipio pedido.
    with mock.patch.object(geo.httpx, "Client", return_value=_client([PARK, TOWN], [])):
        r = geo.geocode_address("Oliva", locality="Oliva")
    assert r["municipality"] == "Oliva" and r["province"] == "Valencia", r

    # 3. Ninguno en el municipio pedido (nombre bilingüe, pedanía) → el primero, como antes.
    with mock.patch.object(geo.httpx, "Client", return_value=_client([PARK], [])):
        r = geo.geocode_address("Calle Mayor 1", locality="Castellón de la Plana")
    assert r["municipality"] == "Pego", r

    print("test_geocode_query: OK (3/3)")


if __name__ == "__main__":
    main()

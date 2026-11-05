"""Self-check: un Notariado caído no se confunde con «zona sin datos».

Sin red ni pytest:  python valuation_api/test_notariado_down.py
Caso real (2026-11-02, Benicàssim): ArcGIS respondía 200 con {"error": …} o vacío,
_query lo leía como «sin datos» y la valoración salía solo con la tasación del
MIVAU (169.000 € para un piso que con el Notariado vale ~339.000 €).
"""
from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mcp_servers.notariado.server as nota  # noqa: E402

ROW = {"precio_m2": 2922.5, "precio_medio": 250000, "superficie_media": 85.0,
       "total": 234, "total_informados": 220, "es_estimado": 0}


def _client(*payloads):
    """httpx.Client falso que devuelve los JSON dados, uno por llamada."""
    resps = []
    for p in payloads:
        r = mock.Mock()
        r.raise_for_status = lambda: None
        r.json.return_value = p
        resps.append(r)
    cli = mock.MagicMock()
    cli.__enter__.return_value.get.side_effect = resps
    return cli


def main() -> None:
    with mock.patch.object(nota.time, "sleep"):
        # 1. 200 con {"error"} y luego bien → el reintento lo salva.
        with mock.patch.object(nota.httpx, "Client",
                               return_value=_client({"error": {"code": 500}}, {"features": [{"attributes": ROW}]})):
            assert nota._query(4, "cp='12560'", "x") == [ROW]

        # 2. Todo vacío y la consulta testigo también → servicio caído: error, no «sin datos».
        with mock.patch.object(nota, "_query", return_value=[]):
            try:
                nota.notariado_price(postal_code="12560", municipality="Benicasim", province="Castellón")
                raise AssertionError("debía lanzar NotariadoUnavailable")
            except nota.NotariadoUnavailable:
                pass

        # 3. Zona sin datos pero el servicio responde (testigo con filas) → found False, como antes.
        testigo = lambda layer, where, out: [{"total": 77467}] if "Madrid" in where else []
        with mock.patch.object(nota, "_query", side_effect=testigo):
            r = nota.notariado_price(postal_code="99999", municipality="Ninguno", province="Ninguna")
            assert r == {"found": False, "reason": "no_data_any_level"}, r

    print("test_notariado_down: OK (3/3)")


if __name__ == "__main__":
    main()

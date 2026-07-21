"""Self-check de contrato del IPV del INE (tabla 79563, base 2025).

Sin pytest:  python valuation_api/test_ipv_contract.py
La parte online pega al INE de verdad: detecta la PRÓXIMA rotación de base
(la 25171, base 2015, quedó histórica el 2026-06-08 congelada en 2025T4 y
seguía respondiendo datos — el ajuste temporal envejecía en silencio).
Se pone en rojo si la serie desaparece, viene vacía o el último periodo
publicado está rancio (>9 meses desde el fin del trimestre).
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_servers.market_research.data_ipv import (  # noqa: E402
    _fetch_items, _quarter, ccaa_for_province, is_stale, pick_trend,
)

# ------------------------- offline (funciones puras) -------------------------

_T1_2026 = time.mktime((2026, 7, 1, 0, 0, 0, 0, 0, -1))  # "hoy" fijado


def test_quarter_mapping():
    # Tempus3: FK_Periodo 19..22 = T1..T4; cualquier otra cosa → None.
    assert [_quarter(q) for q in (19, 20, 21, 22)] == [1, 2, 3, 4]
    assert _quarter(7) is None and _quarter(None) is None


def test_is_stale():
    # 2026T1 visto en julio-2026: fresco. 2025T4 (la 25171 congelada): aún
    # dentro de los 9 meses. 2025T1: rancio. Sin año/trimestre: rancio.
    assert is_stale(2026, 1, now=_T1_2026) is False
    assert is_stale(2025, 4, now=_T1_2026) is False
    assert is_stale(2025, 1, now=_T1_2026) is True
    assert is_stale(None, 1, now=_T1_2026) is True
    assert is_stale(2026, None, now=_T1_2026) is True


def test_pick_trend_data_as_of():
    items = [{
        "Nombre": "Madrid, Comunidad de. General. Variación anual. ",
        "Data": [{"Valor": 13.6, "Anyo": 2026, "FK_Periodo": 19}],
    }]
    t = pick_trend(items, "Madrid, Comunidad de")
    assert t and t["annual_pct"] == 13.6, t
    assert t["period"] == "2026T1" and t["data_as_of"] == "2026T1", t
    assert "stale" in t


# --------------------------- online (contrato INE) ---------------------------

def test_contrato_tabla_vigente():
    items = _fetch_items()
    assert items, "el INE no devolvió datos (¿tabla 79563 retirada o red caída?)"
    # CCAA de control + nacional, serie General y de segunda mano (la que
    # usa el motor para 'usada').
    for construction in ("", "usada"):
        t = pick_trend(items, ccaa_for_province("Madrid"), construction)
        assert t, f"serie no encontrada (construction={construction!r}): " \
                  "¿ha rotado la base del INE? Buscar la tabla nueva y " \
                  "actualizar IPV_URL en data_ipv.py"
        assert t["annual_pct"] is not None
        assert not t["stale"], (
            f"último periodo {t['data_as_of']} rancio: la tabla ha dejado de "
            "actualizarse (rotación de base del INE) — actualizar IPV_URL")


if __name__ == "__main__":
    checks = [v for k, v in sorted(globals().items())
              if k.startswith("test_") and callable(v)]
    for fn in checks:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(checks)} checks passed")

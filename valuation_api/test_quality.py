"""Self-check: control de calidad de la valoración (engine.quality_check).

Sin red ni pytest:  python valuation_api/test_quality.py
Lo que mueve el precio ≥5 % no puede faltar ni fallar en silencio (2026-11-05:
Oliva valorado en Pego, Benicàssim valorado solo con el MIVAU).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from valuation_api.engine import quality_check  # noqa: E402

OK = dict(precision="street", postal_code="12560", property_type="piso", condition_assumed=False,
          floor=5, has_elevator=True, is_attic=False, exterior=True, year_built=1975,
          notariado_level="codigo_postal", catastro_down=False, value_per_m2=3300, base_per_m2=3200)


def fields(q):
    return [m["field"] for m in q["missing"]]


def main() -> None:
    q = quality_check(**OK)
    assert q["ok"] and not q["missing"] and not q["failed_sources"] and not q["extreme"], q

    # Oliva (Informe de Captación): sin calle ni CP, sin tipo, sin estado ni año.
    q = quality_check(**{**OK, "precision": "locality", "postal_code": "", "property_type": "",
                         "condition_assumed": True, "floor": None, "exterior": None, "year_built": 0})
    assert fields(q) == ["address", "postal_code", "property_type", "condition", "year_built"], q
    assert not q["ok"]

    # Piso: planta desconocida; 3º+ sin saber el ascensor; bajo-2º el ascensor da igual.
    assert fields(quality_check(**{**OK, "floor": None, "exterior": None})) == ["floor", "exterior"]
    assert fields(quality_check(**{**OK, "floor": 4, "has_elevator": None})) == ["has_elevator"]
    assert fields(quality_check(**{**OK, "floor": 2, "has_elevator": None})) == []
    # Ático y casa: ni planta ni exterior.
    assert fields(quality_check(**{**OK, "property_type": "atico", "floor": None, "exterior": None})) == []
    assert fields(quality_check(**{**OK, "property_type": "chalet", "floor": None, "exterior": None})) == []

    # Fuentes: Catastro caído, sin Notariado, Notariado solo provincial.
    q = quality_check(**{**OK, "catastro_down": True})
    assert [f["source"] for f in q["failed_sources"]] == ["catastro"] and q["failed_sources"][0]["transient"]
    assert quality_check(**{**OK, "notariado_level": None})["failed_sources"][0]["source"] == "notariado"
    assert quality_check(**{**OK, "notariado_level": "provincia"})["failed_sources"][0]["source"] == "notariado"
    assert not quality_check(**{**OK, "notariado_level": "municipio"})["failed_sources"]

    # Extremo: el piso de 70 m² de Benicàssim (4.943 €/m² sobre 3.170 de base) → +56 %.
    q = quality_check(**{**OK, "value_per_m2": 4943, "base_per_m2": 3170})
    assert q["extreme"] and q["deviation_pct"] == 55.9 and q["ok"], q
    assert quality_check(**{**OK, "value_per_m2": 4489, "base_per_m2": 3220})["extreme"]  # el mismo hoy: +39 %
    assert not quality_check(**{**OK, "value_per_m2": 4100, "base_per_m2": 3170})["extreme"]  # +29 %

    print("test_quality: OK")


if __name__ == "__main__":
    main()

"""
Guardrails compartidos — validación de inputs y outputs.

Production-ready significa que el agente NO inventa a ciegas: valida lo que
entra y comprueba que lo que sale es plausible. Cuando algo no cuadra, marca
"requiere revisión" en vez de devolver un número erróneo con confianza.

Dos capas:
  - Input validators: rechazan datos imposibles (CP mal, m² absurdos, año futuro).
  - Output validators: marcan valoraciones fuera de rangos de mercado España, o
    que divergen demasiado de las fuentes oficiales (señal de revisión humana).
"""

from __future__ import annotations

from typing import Any

# Límites de cordura del mercado residencial español 2026.
MIN_SURFACE_M2 = 10
MAX_SURFACE_M2 = 2000
MIN_YEAR = 1800
MAX_YEAR = 2027
MIN_EUR_M2 = 200
MAX_EUR_M2 = 25000
MIN_VALUE_EUR = 10000
MAX_VALUE_EUR = 50_000_000

VALID_CONDITIONS = {
    "obra_nueva", "nuevo", "reformado", "buen_estado", "a_reformar", "ruina",
}

# Umbral de convergencia entre fuentes oficiales por debajo del cual se
# recomienda revisión humana (transacción real muy lejos de la tasación).
CONVERGENCE_REVIEW_THRESHOLD = 60  # %


# ── Input validation ────────────────────────────────────────────────────

def validate_postal_code(cp: str) -> str | None:
    """Devuelve mensaje de error si el CP español no es válido, o None."""
    if not cp:
        return None  # opcional
    cp = cp.strip()
    if not (cp.isdigit() and len(cp) == 5):
        return f"postal_code inválido: '{cp}' (deben ser 5 dígitos)"
    prov = int(cp[:2])
    if not (1 <= prov <= 52):
        return f"postal_code inválido: provincia '{cp[:2]}' fuera de rango (01-52)"
    return None


def validate_surface(surface_m2: float) -> str | None:
    if surface_m2 is None or surface_m2 <= 0:
        return "surface_m2 debe ser > 0"
    if not (MIN_SURFACE_M2 <= surface_m2 <= MAX_SURFACE_M2):
        return f"surface_m2 fuera de rango plausible ({MIN_SURFACE_M2}-{MAX_SURFACE_M2}): {surface_m2}"
    return None


def validate_year(year: int) -> str | None:
    if not year:
        return None  # desconocido es aceptable
    if not (MIN_YEAR <= year <= MAX_YEAR):
        return f"year_built fuera de rango ({MIN_YEAR}-{MAX_YEAR}): {year}"
    return None


def validate_condition(condition: str) -> str | None:
    if condition and condition not in VALID_CONDITIONS:
        return f"condition desconocida: '{condition}' (válidas: {sorted(VALID_CONDITIONS)})"
    return None


def validate_inputs(**kwargs) -> list[str]:
    """Valida un conjunto de inputs. Devuelve lista de errores (vacía = ok)."""
    errors: list[str] = []
    validators = {
        "postal_code": validate_postal_code,
        "surface_m2": validate_surface,
        "year_built": validate_year,
        "year": validate_year,
        "condition": validate_condition,
    }
    for key, val in kwargs.items():
        if key in validators and val is not None:
            err = validators[key](val)
            if err:
                errors.append(err)
    return errors


# ── Output validation ────────────────────────────────────────────────────

def validate_valuation(value_eur: float, value_eur_per_m2: float) -> list[str]:
    """Marca warnings si una valoración está fuera de rangos de mercado."""
    warnings: list[str] = []
    if value_eur_per_m2 is not None and not (MIN_EUR_M2 <= value_eur_per_m2 <= MAX_EUR_M2):
        warnings.append(
            f"€/m² resultante ({value_eur_per_m2}) fuera del rango España "
            f"({MIN_EUR_M2}-{MAX_EUR_M2}) — revisar inputs")
    if value_eur is not None and not (MIN_VALUE_EUR <= value_eur <= MAX_VALUE_EUR):
        warnings.append(
            f"Valor total ({value_eur}) fuera de rango plausible — revisar")
    return warnings


def assess_source_agreement(
    notariado_price: float | None, mitma_price: float | None,
) -> dict[str, Any]:
    """Evalúa la concordancia entre las dos fuentes oficiales de precio.

    Returns: {convergence_pct, agreement, requires_review, note}
    """
    if not notariado_price or not mitma_price:
        return {
            "convergence_pct": None,
            "agreement": "single_source",
            "requires_review": False,
            "note": "Solo una fuente oficial disponible; sin triangulación.",
        }
    conv = round(min(notariado_price, mitma_price) / max(notariado_price, mitma_price) * 100)
    requires = conv < CONVERGENCE_REVIEW_THRESHOLD
    if conv >= 85:
        agreement, note = "high", "Fuentes muy concordantes — valoración robusta."
    elif conv >= CONVERGENCE_REVIEW_THRESHOLD:
        agreement, note = "moderate", (
            "Divergencia moderada transacción vs tasación (típico en zonas de "
            "alta o baja demanda).")
    else:
        agreement, note = "low", (
            "Divergencia alta entre precio real y tasación — se recomienda "
            "revisión humana antes de fijar precio.")
    return {
        "convergence_pct": conv,
        "agreement": agreement,
        "requires_review": requires,
        "note": note,
    }

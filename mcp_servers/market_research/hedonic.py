"""
Modelo hedónico de valoración inmobiliaria.

Un AVM (Automated Valuation Model) profesional no aplica un multiplicador
plano por estado — ajusta el €/m² base de la zona por las características del
inmueble con coeficientes calibrados. Aquí codificamos los ajustes estándar
del mercado residencial español 2026.

Cada factor devuelve un MULTIPLICADOR sobre el €/m² base. El valor final es:

    €/m²_final = €/m²_zona × Π(factores aplicables)
    valor = €/m²_final × superficie

Limitación honesta: los coeficientes son heurísticas de dominio (lo que aplica
un tasador con experiencia), no calibrados con regresión sobre transacciones
reales. La calibración con datos de Idealista Data / Registradores es el
roadmap M2 — convertiría esto en un AVM estadístico completo.
"""

from __future__ import annotations

from typing import Any

# ── 1. Superficie (no lineal) ──────────────────────────────────────────────
# Pisos pequeños tienen mayor €/m² (más demanda, escasez); pisos muy grandes
# menor €/m² (menos compradores, "descuento por tamaño").
def surface_factor(surface_m2: float) -> float:
    if surface_m2 <= 0:
        return 1.0
    if surface_m2 < 50:
        return 1.08
    if surface_m2 < 80:
        return 1.03
    if surface_m2 < 120:
        return 1.00  # banda de referencia
    if surface_m2 < 180:
        return 0.95
    return 0.90


# ── 2. Planta + ascensor ───────────────────────────────────────────────────
# El factor más infravalorado en valoraciones de juguete. En España, un 3º sin
# ascensor pierde mucho valor; un ático o planta alta CON ascensor gana.
def floor_elevator_factor(floor: int | None, has_elevator: bool | None,
                          is_attic: bool = False) -> float:
    if is_attic:
        return 1.12
    if floor is None:
        return 1.0
    if floor == 0:  # bajo
        return 0.92
    if has_elevator is False:
        if floor <= 2:
            return 1.00
        if floor == 3:
            return 0.90
        return 0.82  # 4º+ sin ascensor: penalización fuerte
    # con ascensor (o desconocido tratado como con ascensor en urbano)
    if floor >= 4:
        return 1.05  # plantas altas con ascensor: luz, vistas, menos ruido
    return 1.00


# ── 3. Eficiencia energética ───────────────────────────────────────────────
# Cada vez más relevante (normativa UE, costes de suministro). Letras peores
# penalizan; las mejores tienen premium creciente.
ENERGY_FACTOR: dict[str, float] = {
    "A": 1.06, "B": 1.03, "C": 1.00, "D": 0.98,
    "E": 0.95, "F": 0.92, "G": 0.90,
}


def energy_factor(rating: str | None) -> float:
    if not rating:
        return 1.0
    return ENERGY_FACTOR.get(rating.strip().upper()[:1], 1.0)


# ── 4. Estado de conservación (gradiente realista) ─────────────────────────
CONDITION_FACTOR: dict[str, float] = {
    "obra_nueva": 1.15,
    "nuevo": 1.15,
    "reformado": 1.08,
    "buen_estado": 1.00,
    "a_reformar": 0.82,   # más realista que el 0.75 plano anterior
    "ruina": 0.60,
}


def condition_factor(condition: str | None) -> float:
    if not condition:
        return 1.0
    return CONDITION_FACTOR.get(condition.strip().lower(), 1.0)


# ── 5. Exterior / interior ─────────────────────────────────────────────────
def orientation_factor(exterior: bool | None) -> float:
    if exterior is None:
        return 1.0
    return 1.00 if exterior else 0.90  # interior: menos luz → menos demanda


# ── 6. Antigüedad (curva fina) ─────────────────────────────────────────────
def antiquity_factor(year_built: int | None) -> float:
    if not year_built:
        return 1.0
    age = max(0, 2026 - year_built)
    if age < 5:
        return 1.10
    if age < 15:
        return 1.05
    if age < 40:
        return 1.00
    if age < 70:
        return 0.94
    if age < 100:
        return 0.88
    return 0.84  # edificios centenarios (salvo rehab integral)


def value_breakdown(
    surface_m2: float,
    base_eur_per_m2: float,
    condition: str | None = None,
    year_built: int | None = None,
    floor: int | None = None,
    has_elevator: bool | None = None,
    is_attic: bool = False,
    energy_rating: str | None = None,
    exterior: bool | None = None,
) -> dict[str, Any]:
    """Aplica el modelo hedónico y devuelve valor + desglose auditable.

    Returns dict con cada factor por separado (transparencia total) + el
    €/m² ajustado y el valor final.
    """
    factors = {
        "surface": round(surface_factor(surface_m2), 4),
        "condition": round(condition_factor(condition), 4),
        "antiquity": round(antiquity_factor(year_built), 4),
        "floor_elevator": round(floor_elevator_factor(floor, has_elevator, is_attic), 4),
        "energy": round(energy_factor(energy_rating), 4),
        "orientation": round(orientation_factor(exterior), 4),
    }

    combined = 1.0
    for f in factors.values():
        combined *= f

    adjusted_eur_m2 = base_eur_per_m2 * combined
    value = round(adjusted_eur_m2 * surface_m2 / 100) * 100  # redondeo a 100€

    return {
        "value_eur": value,
        "value_eur_per_m2": round(adjusted_eur_m2),
        "base_eur_per_m2": round(base_eur_per_m2),
        "combined_factor": round(combined, 4),
        "factors": factors,
        "model": "hedonic_v1",
    }

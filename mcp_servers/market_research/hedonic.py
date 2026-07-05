"""
Modelo hedónico de valoración inmobiliaria (v2).

Un AVM (Automated Valuation Model) profesional no aplica un multiplicador
plano por estado — ajusta el €/m² base de la zona por las características del
inmueble con coeficientes calibrados. Aquí codificamos los ajustes estándar
del mercado residencial español 2026.

Cada factor devuelve un MULTIPLICADOR sobre el €/m² base. El valor final es:

    €/m²_final = €/m²_zona × Π(factores aplicables)
    valor = €/m²_final × superficie

v2 añade sobre v1:
  - Distribución: nº de baños y densidad m²/habitación (el 2º baño es de los
    predictores más fuertes tras superficie y ubicación).
  - Orientación real (N/S/E/O y combinadas), no solo exterior/interior.
  - Extras: terraza, garaje incluido, trastero, piscina/zonas comunes.
  - Tri-estado honesto: ascensor y exterior desconocidos aplican factor NEUTRO
    (v1 asumía optimistamente ascensor=sí y exterior=sí si no se indicaban).

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
#
# v3: curva RELATIVA a la superficie media de la zona. El €/m² del Notariado
# es la mediana de compraventas de la zona, cuyo tamaño medio publica el propio
# Notariado (`superficie_media`, p.ej. 94 m² en CP 12006). Un piso de 50 m² en
# esa zona cotiza muy por encima de esa mediana (caso real: vendido a 2.160
# €/m² vs mediana 1.268): €/m² ≈ mediana × (media_zona/superficie)^alpha.
# Calibración de alpha (2026-07-05, dos fuentes agregadas independientes):
# Fotocasa Castellón may-2026: 1D/estudios 2.567 €/m² vs media 1.977 (+30%)
# → (94/50)^alpha = 1.30 → alpha ≈ 0.41; idealista18 (Madrid/BCN/VLC): pisos
# 40-60 m² cotizan +20-40% sobre la media de zona. ponytail: alpha global;
# el upgrade es por-ciudad con el bucle de cierres reales de los agentes.
_SURFACE_ALPHA = 0.40
_SURFACE_REL_MIN, _SURFACE_REL_MAX = 0.80, 1.35


def surface_factor(surface_m2: float, zone_avg_m2: float | None = None) -> float:
    if surface_m2 <= 0:
        return 1.0
    # Con superficie media de la zona (del Notariado): curva continua relativa.
    if zone_avg_m2 and zone_avg_m2 > 0:
        raw = (zone_avg_m2 / surface_m2) ** _SURFACE_ALPHA
        return max(_SURFACE_REL_MIN, min(_SURFACE_REL_MAX, raw))
    # Sin ella (fallback MITMA/1800): bandas absolutas de siempre.
    if surface_m2 < 40:
        return 1.15
    if surface_m2 < 55:
        return 1.10
    if surface_m2 < 80:
        return 1.04
    if surface_m2 < 120:
        return 1.00  # banda de referencia
    if surface_m2 < 180:
        return 0.95
    return 0.90


# ── 2. Planta + ascensor ───────────────────────────────────────────────────
# El factor más infravalorado en valoraciones de juguete. En España, un 3º sin
# ascensor pierde mucho valor; un ático o planta alta CON ascensor gana.
# has_elevator=None (desconocido) NO aplica premium ni castigo: neutro.
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
    if has_elevator is True and floor >= 4:
        return 1.05  # plantas altas con ascensor: luz, vistas, menos ruido
    return 1.00  # ascensor desconocido o plantas 1-3 con ascensor: neutro


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


# ── 5. Orientación + exterior/interior ─────────────────────────────────────
# En España el sur manda (luz y demanda); el norte penaliza. Interior pierde
# siempre (la penalización de luz domina sobre la orientación, que se ignora).
ORIENTATION_FACTOR: dict[str, float] = {
    "sur": 1.03, "sureste": 1.02, "suroeste": 1.02,
    "este": 1.00, "oeste": 1.00,
    "noreste": 0.98, "noroeste": 0.98, "norte": 0.97,
}


def orientation_factor(exterior: bool | None, orientation: str | None = None) -> float:
    if exterior is False:
        return 0.90  # interior: menos luz → menos demanda (orientación irrelevante)
    if orientation:
        return ORIENTATION_FACTOR.get(orientation.strip().lower(), 1.0)
    return 1.0  # exterior sin orientación conocida, o todo desconocido: neutro


# ── 6. Antigüedad ──────────────────────────────────────────────────────────
# v3: RELATIVA al parque de la zona cuando se conoce el año típico de
# construcción de la sección censal (Censo/INE): el €/m² base ya refleja el
# stock típico, así que lo que se paga es la DIFERENCIA — un edificio del 2000
# en un barrio de los 70 es de lo mejor del parque (+premium); el mismo
# edificio en un PAU del 2005 es simplemente normal (neutro). Sin dato de zona:
# bandas absolutas de siempre. ponytail: 0.3%/año y cota ±10% de partida;
# calibrar con cierres.
_ANTIQ_REL_PER_YEAR = 0.003
_ANTIQ_REL_MIN, _ANTIQ_REL_MAX = 0.90, 1.10


def antiquity_factor(year_built: int | None,
                     zone_typical_year: int | None = None) -> float:
    if not year_built:
        return 1.0
    if zone_typical_year and zone_typical_year > 1500:
        delta = year_built - zone_typical_year
        return max(_ANTIQ_REL_MIN,
                   min(_ANTIQ_REL_MAX, 1 + delta * _ANTIQ_REL_PER_YEAR))
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


# ── 7. Distribución: baños y densidad de habitaciones ──────────────────────
# El 2º baño es de los predictores más fuertes tras superficie y ubicación.
# Un único baño en un piso grande penaliza; demasiadas habitaciones para los
# m² (sobredivisión, habitaciones enanas) también.
def distribution_factor(surface_m2: float, bedrooms: int | None,
                        bathrooms: int | None) -> float:
    f = 1.0
    if bathrooms and surface_m2 > 0:
        if bathrooms >= 2 and surface_m2 >= 80:
            f *= 1.03
        elif bathrooms == 1 and surface_m2 >= 110:
            f *= 0.96
    if bedrooms and surface_m2 > 0:
        if surface_m2 / bedrooms < 16:  # sobredivisión: habitaciones enanas
            f *= 0.95
    return f


# ── 8. Extras: terraza, garaje, trastero, piscina ──────────────────────────
# Solo premian si constan (True); ausentes o desconocidos = neutro, que es el
# default conservador correcto.
def extras_factor(has_terrace: bool = False, has_garage: bool = False,
                  has_storage_room: bool = False, has_pool: bool = False) -> float:
    f = 1.0
    if has_terrace:
        f *= 1.04
    if has_garage:
        f *= 1.05  # plaza incluida en el precio
    if has_storage_room:
        f *= 1.01
    if has_pool:
        f *= 1.02  # piscina / zonas comunes
    return f


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
    orientation: str | None = None,
    bedrooms: int | None = None,
    bathrooms: int | None = None,
    has_terrace: bool = False,
    has_garage: bool = False,
    has_storage_room: bool = False,
    has_pool: bool = False,
    zone_avg_surface_m2: float | None = None,
    zone_typical_year: int | None = None,
) -> dict[str, Any]:
    """Aplica el modelo hedónico y devuelve valor + desglose auditable.

    Returns dict con cada factor por separado (transparencia total) + el
    €/m² ajustado, el valor final y la lista de campos desconocidos a los
    que se aplicó factor neutro (`unknown_inputs`).
    """
    factors = {
        "surface": round(surface_factor(surface_m2, zone_avg_surface_m2), 4),
        "condition": round(condition_factor(condition), 4),
        "antiquity": round(antiquity_factor(year_built, zone_typical_year), 4),
        "floor_elevator": round(floor_elevator_factor(floor, has_elevator, is_attic), 4),
        "energy": round(energy_factor(energy_rating), 4),
        "orientation": round(orientation_factor(exterior, orientation), 4),
        "distribution": round(distribution_factor(surface_m2, bedrooms, bathrooms), 4),
        "extras": round(extras_factor(has_terrace, has_garage,
                                      has_storage_room, has_pool), 4),
    }

    combined = 1.0
    for f in factors.values():
        combined *= f

    adjusted_eur_m2 = base_eur_per_m2 * combined
    value = round(adjusted_eur_m2 * surface_m2 / 100) * 100  # redondeo a 100€

    # Transparencia: campos sin dato → factor neutro (el consumidor decide si
    # pedirlos al usuario o mostrarlos como "no considerado").
    unknown_inputs = [name for name, missing in {
        "condition": not condition,
        "year_built": not year_built,
        "floor": floor is None and not is_attic,
        "has_elevator": has_elevator is None and not is_attic,
        "energy_rating": not energy_rating,
        "orientation": exterior is None and not orientation,
        "bedrooms": not bedrooms,
        "bathrooms": not bathrooms,
    }.items() if missing]

    return {
        "value_eur": value,
        "value_eur_per_m2": round(adjusted_eur_m2),
        "base_eur_per_m2": round(base_eur_per_m2),
        "combined_factor": round(combined, 4),
        "factors": factors,
        "unknown_inputs": unknown_inputs,
        "model": "hedonic_v2",
    }

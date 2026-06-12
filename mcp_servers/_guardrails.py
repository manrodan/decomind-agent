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

VALID_ORIENTATIONS = {
    "norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste",
}

# Prefijo INE del CP (2 primeros dígitos) → alias normalizados (sin acentos,
# minúsculas) de la provincia, incluyendo variantes cooficiales e históricas.
# Permite detectar un CP que no corresponde a la provincia del inmueble (si se
# usara, el Notariado devolvería precios de OTRA provincia).
PROVINCE_ALIASES_BY_CP_PREFIX: dict[str, set[str]] = {
    "01": {"alava", "araba"}, "02": {"albacete"},
    "03": {"alicante", "alacant"}, "04": {"almeria"}, "05": {"avila"},
    "06": {"badajoz"},
    "07": {"baleares", "illes balears", "islas baleares"},
    "08": {"barcelona"}, "09": {"burgos"}, "10": {"caceres"},
    "11": {"cadiz"}, "12": {"castellon", "castello"},
    "13": {"ciudad real"}, "14": {"cordoba"},
    "15": {"a coruna", "la coruna", "coruna"}, "16": {"cuenca"},
    "17": {"girona", "gerona"}, "18": {"granada"}, "19": {"guadalajara"},
    "20": {"guipuzcoa", "gipuzkoa"}, "21": {"huelva"}, "22": {"huesca"},
    "23": {"jaen"}, "24": {"leon"}, "25": {"lleida", "lerida"},
    "26": {"la rioja"}, "27": {"lugo"}, "28": {"madrid"}, "29": {"malaga"},
    "30": {"murcia", "region de murcia"},
    "31": {"navarra", "nafarroa", "comunidad foral de navarra"},
    "32": {"ourense", "orense"},
    "33": {"asturias", "principado de asturias"}, "34": {"palencia"},
    "35": {"las palmas"}, "36": {"pontevedra"}, "37": {"salamanca"},
    "38": {"santa cruz de tenerife", "tenerife"}, "39": {"cantabria"},
    "40": {"segovia"}, "41": {"sevilla"}, "42": {"soria"},
    "43": {"tarragona"}, "44": {"teruel"}, "45": {"toledo"},
    "46": {"valencia"}, "47": {"valladolid"},
    "48": {"vizcaya", "bizkaia"}, "49": {"zamora"}, "50": {"zaragoza"},
    "51": {"ceuta"}, "52": {"melilla"},
}


def _norm_province(name: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def cp_matches_province(cp: str, province: str) -> bool | None:
    """¿El CP corresponde a la provincia? True/False, o None si no se puede
    determinar (CP inválido, provincia vacía o nombre no reconocido)."""
    cp = (cp or "").strip()
    if not (cp.isdigit() and len(cp) == 5):
        return None
    aliases = PROVINCE_ALIASES_BY_CP_PREFIX.get(cp[:2])
    prov = _norm_province(province)
    if not aliases or not prov:
        return None
    return prov in aliases

MAX_FLOOR = 60
MAX_BEDROOMS = 20
MAX_BATHROOMS = 15

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


def validate_orientation(orientation: str) -> str | None:
    if orientation and orientation.strip().lower() not in VALID_ORIENTATIONS:
        return (f"orientation desconocida: '{orientation}' "
                f"(válidas: {sorted(VALID_ORIENTATIONS)})")
    return None


def validate_floor(floor: int) -> str | None:
    if not (0 <= floor <= MAX_FLOOR):
        return f"floor fuera de rango (0-{MAX_FLOOR}): {floor}"
    return None


def validate_bedrooms(bedrooms: int) -> str | None:
    if not (1 <= bedrooms <= MAX_BEDROOMS):
        return f"bedrooms fuera de rango (1-{MAX_BEDROOMS}): {bedrooms}"
    return None


def validate_bathrooms(bathrooms: int) -> str | None:
    if not (1 <= bathrooms <= MAX_BATHROOMS):
        return f"bathrooms fuera de rango (1-{MAX_BATHROOMS}): {bathrooms}"
    return None


def validate_inputs(**kwargs) -> list[str]:
    """Valida un conjunto de inputs. Devuelve lista de errores (vacía = ok).

    Solo valida los campos presentes y no-None — los desconocidos son
    aceptables (el modelo les aplica factor neutro)."""
    errors: list[str] = []
    validators = {
        "postal_code": validate_postal_code,
        "surface_m2": validate_surface,
        "year_built": validate_year,
        "year": validate_year,
        "condition": validate_condition,
        "orientation": validate_orientation,
        "floor": validate_floor,
        "bedrooms": validate_bedrooms,
        "bathrooms": validate_bathrooms,
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

"""
Tabla de referencia de €/m² por provincia y por distrito de ciudades grandes.

Fuente: agregación de datos públicos (INE 2025-Q1, Tinsa IMIE 2025, Notarios CIEN).
Valores expresados en EUR por m² construido, mediana de vivienda usada.

Usado como base por el proveedor sintético de comparables (MVP del challenge).
Roadmap post-challenge: integración con proveedores oficiales con contrato
(Idealista Data, Tinsa API, microdatos INE). No se contempla scraping.
"""

from __future__ import annotations

# Mediana €/m² por provincia (datos públicos 2025-Q1).
PROVINCE_PRICE_PER_SQM: dict[str, float] = {
    "madrid": 4250,
    "barcelona": 4100,
    "guipuzcoa": 3850,
    "vizcaya": 3100,
    "baleares": 4400,
    "malaga": 3050,
    "valencia": 2150,
    "alava": 2700,
    "navarra": 2400,
    "cadiz": 2200,
    "santa cruz de tenerife": 2750,
    "las palmas": 2650,
    "girona": 2700,
    "sevilla": 2100,
    "tarragona": 2050,
    "asturias": 1750,
    "zaragoza": 1900,
    "valladolid": 1750,
    "la coruña": 1700,
    "pontevedra": 1700,
    "leon": 1300,
    "cordoba": 1400,
    "huelva": 1450,
    "murcia": 1500,
    "alicante": 2050,
    "castellon": 1500,
    "salamanca": 1650,
    "burgos": 1600,
    "lugo": 1300,
    "ourense": 1250,
    "albacete": 1200,
    "ciudad real": 1100,
    "toledo": 1350,
    "guadalajara": 1500,
    "cuenca": 1100,
    "caceres": 1150,
    "badajoz": 1150,
    "jaen": 1100,
    "almeria": 1500,
    "granada": 1700,
    "huesca": 1500,
    "teruel": 1100,
    "soria": 1250,
    "segovia": 1500,
    "avila": 1300,
    "palencia": 1300,
    "zamora": 1100,
    "la rioja": 1700,
    "cantabria": 2050,
    "ceuta": 1900,
    "melilla": 1900,
    "lleida": 1500,
}

# Ajuste por distrito en grandes ciudades — multiplicador sobre la mediana provincial.
# Capturar barrios premium y barrios populares para que la valoración refleje la zona.
DISTRICT_MULTIPLIER: dict[tuple[str, str], float] = {
    # Madrid (provincia: 4250 €/m²)
    ("madrid", "salamanca"): 1.55,
    ("madrid", "chamberi"): 1.45,
    ("madrid", "chamartin"): 1.40,
    ("madrid", "centro"): 1.30,
    ("madrid", "retiro"): 1.50,
    ("madrid", "moncloa-aravaca"): 1.35,
    ("madrid", "tetuan"): 1.10,
    ("madrid", "arganzuela"): 1.20,
    ("madrid", "ciudad lineal"): 1.00,
    ("madrid", "carabanchel"): 0.70,
    ("madrid", "usera"): 0.65,
    ("madrid", "puente de vallecas"): 0.60,
    ("madrid", "villaverde"): 0.55,
    ("madrid", "san blas-canillejas"): 0.85,
    ("madrid", "latina"): 0.75,
    # Barcelona (provincia: 4100 €/m²)
    ("barcelona", "sarria-sant gervasi"): 1.55,
    ("barcelona", "les corts"): 1.40,
    ("barcelona", "eixample"): 1.35,
    ("barcelona", "gracia"): 1.20,
    ("barcelona", "ciutat vella"): 1.15,
    ("barcelona", "sant marti"): 1.05,
    ("barcelona", "horta-guinardo"): 0.85,
    ("barcelona", "nou barris"): 0.65,
    ("barcelona", "sant andreu"): 0.85,
    ("barcelona", "sants-montjuic"): 0.95,
}

# Ajuste por estado del inmueble (multiplicador sobre la mediana de comparables).
CONDITION_MULTIPLIER: dict[str, float] = {
    "nuevo": 1.20,
    "buen_estado": 1.00,
    "a_reformar": 0.75,
}

# Ajuste por antigüedad (años) — penalización suave.
def antiquity_multiplier(year_built: int | None) -> float:
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
        return 0.92
    return 0.85


def base_price_per_sqm(province: str | None, district: str | None) -> float:
    """Devuelve €/m² base para una provincia/distrito. Default fallback España: 1800."""
    if not province:
        return 1800.0
    p = province.strip().lower()
    base = PROVINCE_PRICE_PER_SQM.get(p, 1800.0)
    if district:
        d = district.strip().lower()
        mult = DISTRICT_MULTIPLIER.get((p, d), 1.0)
        return base * mult
    return base

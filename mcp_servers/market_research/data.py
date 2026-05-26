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


_PROVINCE_PREFIXES = (
    "comunidad de ", "comunidad foral de ", "comunitat de ",
    "principado de ", "region de ", "província de ", "provincia de ",
    "comunitat valenciana", "comunidad valenciana",
)
_PROVINCE_ALIASES: dict[str, str] = {
    "comunitat valenciana": "valencia",
    "comunidad valenciana": "valencia",
    "comunidad foral de navarra": "navarra",
    "principado de asturias": "asturias",
    "region de murcia": "murcia",
    "illes balears": "baleares",
    "islas baleares": "baleares",
    "araba/alava": "alava",
    "araba / alava": "alava",
    "gipuzkoa": "guipuzcoa",
    "bizkaia": "vizcaya",
    "a coruna": "la coruna",
    "a coruña": "la coruña",
}

# Alias de municipios con doble nomenclatura (valenciano/catalán/euskera/galego).
# Aplicado en _norm tras quitar acentos — claves SIN acentos.
# La clave es la forma "secundaria" (la que devuelve Nominatim o el usuario),
# el valor es la forma canónica que coincide con MITMA.
_MUNICIPALITY_ALIASES: dict[str, str] = {
    # Valenciano / castellano
    "benicasim": "benicassim",
    "alcoi": "alcoy",
    "alacant": "alicante",
    "castello de la plana": "castellon de la plana",
    "castello": "castellon de la plana",
    "elx": "elche",
    "xativa": "jativa",
    "ondara": "ondara",
    "gandia": "gandia",
    "oriola": "orihuela",
    # Catalán / castellano
    "lleida": "lerida",
    "girona": "gerona",
    "vic": "vich",
    # Euskera / castellano
    "donostia": "san sebastian",
    "donostia / san sebastian": "san sebastian",
    "donostia/san sebastian": "san sebastian",
    "vitoria-gasteiz": "vitoria",
    "iruna": "pamplona",
    # Galego / castellano
    "a coruna": "la coruna",
    "ourense": "orense",
    "sanxenxo": "sangenjo",
}


def _norm(s: str | None) -> str:
    """lowercase + sin acentos + colapsar espacios + alias administrativos."""
    if not s:
        return ""
    import re
    import unicodedata
    out = s.strip().lower()
    out = "".join(c for c in unicodedata.normalize("NFD", out) if unicodedata.category(c) != "Mn")
    out = re.sub(r"\s+", " ", out)
    if out in _PROVINCE_ALIASES:
        return _PROVINCE_ALIASES[out]
    if out in _MUNICIPALITY_ALIASES:
        return _MUNICIPALITY_ALIASES[out]
    for prefix in _PROVINCE_PREFIXES:
        if out.startswith(prefix):
            stripped = out[len(prefix):].strip()
            if stripped:
                return stripped
    return out


def resolve_base_price(
    province: str | None,
    district: str | None,
    municipality: str | None = None,
) -> tuple[float, str]:
    """Devuelve (€/m² base, source_label). Fuente única de verdad — el call site
    obtiene precio y etiqueta de procedencia consistentes.

    Cadena de preferencia:
      1. MITMA municipio (dato oficial Ministerio de Transportes)
      2. Provincia estática × multiplicador distrito (curado Madrid/BCN)
      3. MITMA provincia (mediana de sus municipios)
      4. Fallback España 1800 €/m²
    """
    try:
        from mcp_servers.market_research.data_mitma import (
            MUNICIPALITY_PRICE_PER_SQM_MITMA,
            PROVINCE_PRICE_PER_SQM_MITMA,
        )
    except ImportError:
        MUNICIPALITY_PRICE_PER_SQM_MITMA = {}
        PROVINCE_PRICE_PER_SQM_MITMA = {}

    p_norm = _norm(province)
    m_norm = _norm(municipality)
    d_norm = _norm(district)

    # 1) MITMA municipio
    if m_norm and m_norm in MUNICIPALITY_PRICE_PER_SQM_MITMA:
        mitma = MUNICIPALITY_PRICE_PER_SQM_MITMA[m_norm]
        if d_norm and (p_norm, d_norm) in DISTRICT_MULTIPLIER:
            return mitma * DISTRICT_MULTIPLIER[(p_norm, d_norm)], "mitma_municipal"
        return mitma, "mitma_municipal"

    # 2) Provincia curada (Madrid/BCN principalmente) × distrito
    if p_norm and p_norm in PROVINCE_PRICE_PER_SQM:
        base = PROVINCE_PRICE_PER_SQM[p_norm]
        if d_norm and (p_norm, d_norm) in DISTRICT_MULTIPLIER:
            return base * DISTRICT_MULTIPLIER[(p_norm, d_norm)], "curated_province"
        return base, "curated_province"

    # 3) MITMA provincia
    if p_norm and p_norm in PROVINCE_PRICE_PER_SQM_MITMA:
        return PROVINCE_PRICE_PER_SQM_MITMA[p_norm], "mitma_province"

    # 4) Fallback España
    return 1800.0, "fallback"


def base_price_per_sqm(
    province: str | None,
    district: str | None,
    municipality: str | None = None,
) -> float:
    """Compatibilidad — solo devuelve el precio (la fuente se consulta con
    resolve_base_price si se necesita etiqueta)."""
    return resolve_base_price(province, district, municipality)[0]

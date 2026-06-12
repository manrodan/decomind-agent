"""
Parser determinista de características de anuncios inmobiliarios españoles.

Convierte la lista de "características" que captura la extensión Clipper de
Decomind desde Idealista (y el texto libre de la descripción) en los inputs
estructurados del modelo hedónico: planta, ascensor, orientación, nº de
habitaciones y baños, extras, estado, año, superficie y letra energética.

Determinista a propósito (regex + normalización, sin LLM): mismo anuncio →
mismos campos, gratis, instantáneo y testeable en evals. Los formatos de
Idealista son muy canónicos ("Planta 4ª exterior con ascensor",
"Orientación sur", "Plaza de garaje incluida en el precio"…), así que la
cobertura real es alta; lo que no se reconoce se devuelve en `unmatched`
para que la UI lo enseñe y el agente lo complete a mano.

Uso:
    parse_property_features(["3 habitaciones", "Planta 3ª exterior", ...],
                            description="Piso muy luminoso...")
    -> {"fields": {bedrooms: 3, floor: 3, exterior: True, ...},
        "matched": [...], "unmatched": [...]}
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

_ORIENTATION_WORDS = (
    "noreste", "noroeste", "sureste", "suroeste",  # compuestas primero
    "norte", "sur", "este", "oeste",
)

# Pares de simples → compuesta canónica del modelo hedónico.
_ORIENTATION_COMBOS = {
    frozenset({"sur", "este"}): "sureste",
    frozenset({"sur", "oeste"}): "suroeste",
    frozenset({"norte", "este"}): "noreste",
    frozenset({"norte", "oeste"}): "noroeste",
}


def _norm(text: str) -> str:
    """minúsculas + sin acentos + compatibilidad unicode (m² → m2, 3ª → 3a)."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower().strip()


def _parse_orientation(s: str) -> str | None:
    m = re.search(r"orientacion\s+([a-z,\s/y-]+)", s)
    if not m:
        return None
    segment = m.group(1)
    found: set[str] = set()
    for word in _ORIENTATION_WORDS:
        if re.search(rf"\b{word}\b", segment):
            # "este" es substring de "noreste"/"sureste": al ir las compuestas
            # primero y usar \b sobre la palabra simple, hay que descartar la
            # simple si ya cayó una compuesta que la contiene.
            if any(word != f and word in f for f in found):
                continue
            found.add(word)
    if not found:
        return None
    if len(found) == 1:
        return next(iter(found))
    combo = _ORIENTATION_COMBOS.get(frozenset(found))
    return combo  # opuestas o 3+ orientaciones → None (neutro, honesto)


def _parse_one(s: str, out: dict[str, Any]) -> bool:
    """Extrae lo que pueda de un string normalizado. True si aportó algo."""
    hit = False

    def put(key: str, value: Any) -> None:
        nonlocal hit
        if key not in out:
            out[key] = value
        hit = True  # aunque ya existiera: el string sí contenía señal

    # superficie ("90 m2 construidos" preferente; "90 m2" como fallback)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*m2\s*construidos", s)
    if not m and "utiles" not in s:
        m = re.search(r"^(\d+(?:[.,]\d+)?)\s*m2\b", s)
    if m:
        put("surface_m2", float(m.group(1).replace(",", ".")))

    # habitaciones y baños
    m = re.search(r"(\d+)\s*(?:habitacion|hab\b|dormitorio)", s)
    if m:
        put("bedrooms", int(m.group(1)))
    m = re.search(r"(\d+)\s*banos?\b", s)
    if m:
        put("bathrooms", int(m.group(1)))

    # año de construcción
    m = re.search(r"construido\s+en\s+(\d{4})", s)
    if m:
        put("year_built", int(m.group(1)))

    # planta / ático / bajo ("planta 4a exterior con ascensor", "bajo interior")
    if re.search(r"\batico\b", s):
        put("is_attic", True)
    # "planta 4a" (4ª normalizada): el ordinal pega la "a" al dígito, sin \b.
    m = re.search(r"planta\s+(\d{1,2})", s) or re.search(r"\b(\d{1,2})a?\s+planta\b", s)
    if m:
        put("floor", int(m.group(1)))
    elif re.search(r"\b(?:bajo|planta baja|entreplanta)\b", s):
        put("floor", 0)

    # ascensor (el "sin" debe ganar al substring "ascensor")
    if re.search(r"\bsin\s+ascensor\b", s):
        put("has_elevator", False)
    elif re.search(r"\bascensor\b", s):
        put("has_elevator", True)

    # exterior / interior (en Idealista van en la línea de planta)
    if re.search(r"\bexterior\b", s) and "carpinteria" not in s:
        put("exterior", True)
    elif re.search(r"\binterior\b", s) and "carpinteria" not in s:
        put("exterior", False)

    # orientación
    orient = _parse_orientation(s)
    if orient:
        put("orientation", orient)

    # estado de conservación (formatos "Segunda mano/buen estado", etc.)
    if re.search(r"(?:para|a)\s+reformar", s):
        put("condition", "a_reformar")
    elif re.search(r"obra\s+nueva", s):
        put("condition", "obra_nueva")
    elif re.search(r"\breformad[oa]\b", s):
        put("condition", "reformado")
    elif re.search(r"buen\s+estado", s):
        put("condition", "buen_estado")

    # letra energética ("consumo: e (135 kwh...)", "calificacion energetica: d")
    m = re.search(
        r"(?:consumo|emisiones|(?:certificacion|calificacion|clase|etiqueta)\s+"
        r"energetica)\s*:?\s*([a-g])\b", s)
    if m:
        put("energy_rating", m.group(1).upper())

    # extras
    if re.search(r"\bterraza\b", s):
        put("has_terrace", True)
    if re.search(r"\btrastero\b", s):
        put("has_storage_room", True)
    if re.search(r"\bpiscina\b", s):
        put("has_pool", True)
    if re.search(r"\bgaraje\b", s):
        # solo cuenta si está incluida en el precio (o no se dice lo contrario)
        if re.search(r"adicional|opcional|alquiler|no\s+incluid", s):
            put("has_garage", False)
        else:
            put("has_garage", True)
    if re.search(r"aire\s+acondicionado", s):
        put("has_air_conditioning", True)

    return hit


def parse_property_features(
    features: list[str] | None,
    description: str = "",
) -> dict[str, Any]:
    """Parsea características de anuncio (Idealista/Clipper) a inputs del modelo.

    Args:
        features: lista de strings tal como los captura el Clipper
            (p.ej. ["3 habitaciones", "Planta 4ª exterior con ascensor"]).
        description: texto libre del anuncio (fallback: solo rellena campos
            que las features no hayan aportado).

    Returns:
        {
          "fields": {surface_m2?, bedrooms?, bathrooms?, year_built?, floor?,
                     is_attic?, has_elevator?, exterior?, orientation?,
                     condition?, energy_rating?, has_terrace?, has_garage?,
                     has_storage_room?, has_pool?, has_air_conditioning?},
          "matched":   [features que aportaron algún campo],
          "unmatched": [features sin señal reconocida],
        }
        Solo aparecen las claves detectadas — lo ausente sigue siendo
        desconocido (el modelo hedónico le aplicará factor neutro).
    """
    fields: dict[str, Any] = {}
    matched: list[str] = []
    unmatched: list[str] = []

    for raw in features or []:
        if not raw or not str(raw).strip():
            continue
        if _parse_one(_norm(str(raw)), fields):
            matched.append(str(raw))
        else:
            unmatched.append(str(raw))

    # La descripción solo complementa: nunca pisa lo que dicen las features.
    if description and description.strip():
        _parse_one(_norm(description), fields)

    return {"fields": fields, "matched": matched, "unmatched": unmatched}

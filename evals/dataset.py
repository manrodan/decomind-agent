"""
Dataset de evaluación — casos con valores esperados.

Cada caso define los inputs de un inmueble + expectativas verificables
(rangos de precio, fuente de datos esperada, año Catastro, etc.). El runner
ejecuta el pipeline real de tools y comprueba estas expectativas.

Las expectativas usan rangos (no valores exactos) porque los datos oficiales
se actualizan mensualmente. Rangos amplios = robustez; estrechos = precisión.
"""

from __future__ import annotations

# ── Casos offline del parser de características (Idealista/Clipper) ─────────
# Formatos reales tal como los captura la extensión: el parser debe extraer
# exactamente estos campos. Sin red: rápidos y 100% deterministas.
PARSER_CASES: list[dict] = [
    {
        "id": "idealista-tipico",
        "features": [
            "90 m² construidos, 78 m² útiles", "3 habitaciones", "2 baños",
            "Terraza", "Plaza de garaje incluida en el precio",
            "Segunda mano/buen estado", "Armarios empotrados",
            "Orientación sur", "Construido en 1995", "Trastero",
            "Planta 4ª exterior con ascensor", "Consumo: E (135 kWh/m² año)",
        ],
        "expect": {
            "surface_m2": 90.0, "bedrooms": 3, "bathrooms": 2,
            "has_terrace": True, "has_garage": True, "has_storage_room": True,
            "condition": "buen_estado", "orientation": "sur",
            "year_built": 1995, "floor": 4, "exterior": True,
            "has_elevator": True, "energy_rating": "E",
        },
    },
    {
        "id": "sin-ascensor-interior",
        "features": [
            "65 m² construidos", "2 habitaciones", "1 baño",
            "Segunda mano/para reformar", "Planta 3ª interior sin ascensor",
            "Orientación norte",
        ],
        "expect": {
            "surface_m2": 65.0, "bedrooms": 2, "bathrooms": 1,
            "condition": "a_reformar", "floor": 3, "exterior": False,
            "has_elevator": False, "orientation": "norte",
        },
    },
    {
        "id": "atico-obra-nueva-combinada",
        "features": [
            "120 m² construidos", "4 habitaciones", "2 baños", "Ático",
            "Promoción de obra nueva", "Piscina", "Orientación sur, oeste",
            "Con ascensor",
        ],
        "expect": {
            "is_attic": True, "condition": "obra_nueva", "has_pool": True,
            "orientation": "suroeste", "has_elevator": True,
            "bedrooms": 4, "bathrooms": 2,
        },
    },
    {
        "id": "bajo-garaje-opcional",
        "features": [
            "Bajo exterior con ascensor",
            "Plaza de garaje opcional por 18.000 €",
            "Calificación energética: D",
        ],
        "expect": {
            "floor": 0, "exterior": True, "has_elevator": True,
            "has_garage": False, "energy_rating": "D",
        },
    },
]

CASES: list[dict] = [
    {
        "id": "madrid-centro",
        "desc": "Madrid Centro — zona prime, edificio antiguo",
        "input": {
            "address": "Calle Mayor 5", "locality": "Madrid",
            "province": "Madrid", "postal_code": "28013",
            "surface_m2": 95, "condition": "a_reformar",
            "rooms": [
                {"kind": "salon", "area_sqm": 24}, {"kind": "kitchen", "area_sqm": 11},
                {"kind": "bathroom", "area_sqm": 5},
                {"kind": "master_bedroom", "area_sqm": 16},
                {"kind": "secondary_bedroom", "area_sqm": 12},
                {"kind": "hallway", "area_sqm": 7},
            ],
            "tier": "standard",
        },
        "expect": {
            "geocode_found": True,
            "catastro_found": True,
            "catastro_year_range": [1850, 1960],
            "notariado_level": ["codigo_postal", "municipio"],
            "notariado_price_range": [4500, 8000],
            "notariado_min_transactions": 50,
            "current_value_range": [250000, 600000],
            "roi_recommendation_in": ["muy_recomendado", "recomendado", "marginal", "no_recomendado"],
        },
    },
    {
        "id": "marbella-costa",
        "desc": "Marbella — costa premium, buen estado",
        "input": {
            "address": "Avenida Ricardo Soriano 30", "locality": "Marbella",
            "province": "Málaga", "postal_code": "29602",
            "surface_m2": 110, "condition": "buen_estado",
            "rooms": [
                {"kind": "salon", "area_sqm": 28}, {"kind": "kitchen", "area_sqm": 12},
                {"kind": "bathroom", "area_sqm": 6}, {"kind": "bathroom", "area_sqm": 5},
                {"kind": "master_bedroom", "area_sqm": 16},
                {"kind": "secondary_bedroom", "area_sqm": 13},
                {"kind": "hallway", "area_sqm": 7},
            ],
            "tier": "standard",
        },
        "expect": {
            "geocode_found": True,
            "catastro_found": True,
            "catastro_year_range": [1960, 2025],
            "notariado_level": ["codigo_postal", "municipio"],
            "notariado_price_range": [2500, 6000],
            "notariado_min_transactions": 30,
            "current_value_range": [300000, 800000],
            "roi_recommendation_in": ["muy_recomendado", "recomendado", "marginal", "no_recomendado"],
        },
    },
    {
        "id": "valencia-ruzafa",
        "desc": "Valencia — capital, mercado activo",
        "input": {
            "address": "Carrer de Cuba 25", "locality": "Valencia",
            "province": "Valencia", "postal_code": "46006",
            "surface_m2": 78, "condition": "a_reformar",
            "rooms": [
                {"kind": "salon", "area_sqm": 20}, {"kind": "kitchen", "area_sqm": 9},
                {"kind": "bathroom", "area_sqm": 5},
                {"kind": "master_bedroom", "area_sqm": 13},
                {"kind": "secondary_bedroom", "area_sqm": 11},
                {"kind": "hallway", "area_sqm": 5},
            ],
            "tier": "standard",
        },
        "expect": {
            "geocode_found": True,
            "catastro_found": True,
            "catastro_year_range": [1900, 2010],
            "notariado_level": ["codigo_postal", "municipio"],
            "notariado_price_range": [1500, 4000],
            "notariado_min_transactions": 30,
            "current_value_range": [120000, 350000],
            "roi_recommendation_in": ["muy_recomendado", "recomendado", "marginal", "no_recomendado"],
        },
    },
    {
        "id": "bilbao-centro",
        "desc": "Bilbao — capital norte, sin multiplicador distrito curado",
        "input": {
            "address": "Calle Iparraguirre 10", "locality": "Bilbao",
            "province": "Bizkaia", "postal_code": "48011",
            "surface_m2": 85, "condition": "a_reformar",
            "rooms": [
                {"kind": "salon", "area_sqm": 22}, {"kind": "kitchen", "area_sqm": 10},
                {"kind": "bathroom", "area_sqm": 5},
                {"kind": "master_bedroom", "area_sqm": 14},
                {"kind": "secondary_bedroom", "area_sqm": 11},
                {"kind": "hallway", "area_sqm": 6},
            ],
            "tier": "standard",
        },
        "expect": {
            "geocode_found": True,
            "catastro_found": True,
            "catastro_year_range": [1900, 2010],
            "notariado_level": ["codigo_postal", "municipio"],
            "notariado_price_range": [2000, 5000],
            "notariado_min_transactions": 20,
            "current_value_range": [150000, 400000],
            "roi_recommendation_in": ["muy_recomendado", "recomendado", "marginal", "no_recomendado"],
        },
    },
    {
        "id": "benicassim-pueblo",
        "desc": "Benicàssim — pueblo costero pequeño (test fallback de granularidad)",
        "input": {
            "address": "Calle Bayer 14", "locality": "Benicàssim",
            "province": "Castellón", "postal_code": "12560",
            "surface_m2": 84, "condition": "a_reformar",
            "rooms": [
                {"kind": "salon", "area_sqm": 22}, {"kind": "kitchen", "area_sqm": 9},
                {"kind": "bathroom", "area_sqm": 4},
                {"kind": "master_bedroom", "area_sqm": 15},
                {"kind": "secondary_bedroom", "area_sqm": 12},
                {"kind": "hallway", "area_sqm": 6},
            ],
            "tier": "standard",
        },
        "expect": {
            "geocode_found": True,
            "catastro_found": True,
            "catastro_year_range": [1900, 2010],
            # pueblo pequeño: puede caer a municipio o provincia
            "notariado_level": ["codigo_postal", "municipio", "provincia"],
            "notariado_price_range": [1000, 3500],
            "notariado_min_transactions": 0,
            "current_value_range": [80000, 300000],
            "roi_recommendation_in": ["muy_recomendado", "recomendado", "marginal", "no_recomendado"],
        },
    },
]

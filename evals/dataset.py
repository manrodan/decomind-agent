"""
Dataset de evaluación — casos con valores esperados.

Cada caso define los inputs de un inmueble + expectativas verificables
(rangos de precio, fuente de datos esperada, año Catastro, etc.). El runner
ejecuta el pipeline real de tools y comprueba estas expectativas.

Las expectativas usan rangos (no valores exactos) porque los datos oficiales
se actualizan mensualmente. Rangos amplios = robustez; estrechos = precisión.
"""

from __future__ import annotations

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

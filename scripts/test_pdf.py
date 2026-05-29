"""Smoke test del PDF con los nuevos campos (doble fuente + hedónico + catastro)."""

from __future__ import annotations

import json

from mcp_servers.dossier_pdf.server import render_dossier_pdf

by_room = [
    {"kind": "salon", "area_sqm": 24, "painting": 432, "masonry": 330,
     "plumbing": 0, "electrical": 680, "labor": 2160, "total_integral": 3602},
    {"kind": "kitchen", "area_sqm": 11, "painting": 198, "masonry": 605,
     "plumbing": 1100, "electrical": 810, "labor": 990, "total_integral": 3703},
    {"kind": "bathroom", "area_sqm": 5, "painting": 90, "masonry": 275,
     "plumbing": 1800, "electrical": 615, "labor": 450, "total_integral": 3230},
    {"kind": "master_bedroom", "area_sqm": 16, "painting": 288, "masonry": 220,
     "plumbing": 0, "electrical": 615, "labor": 1440, "total_integral": 2563},
    {"kind": "secondary_bedroom", "area_sqm": 12, "painting": 216, "masonry": 165,
     "plumbing": 0, "electrical": 615, "labor": 1080, "total_integral": 2076},
    {"kind": "hallway", "area_sqm": 7, "painting": 126, "masonry": 96,
     "plumbing": 0, "electrical": 550, "labor": 630, "total_integral": 1402},
]

result = render_dossier_pdf(
    property_address="Calle Mayor 5",
    property_municipality="Madrid",
    property_district="Centro",
    property_surface_m2=95,
    property_year_built=1914,
    property_condition="a_reformar",
    median_price_eur_per_m2=5919,
    data_source="notariado_codigo_postal",
    current_value_eur=410000,
    post_reno_value_eur=540000,
    renovation_total_integral_eur=16576,
    renovation_tier="standard",
    by_room=by_room,
    roi_net_gain_eur=113424,
    roi_payback_ratio=7.84,
    roi_recommendation="muy_recomendado",
    agent_verdict="Strong investment opportunity: real notarial transactions in "
                  "postal code 28013 confirm a premium location. The renovation "
                  "yields an estimated net gain of 113.000 EUR.",
    property_features=["No elevator", "Energy rating E", "2 bedrooms",
                       "Built in 1914", "Exterior"],
    notariado_price_m2=5919,
    notariado_transactions=286,
    notariado_level="codigo_postal",
    mitma_price_m2=5286,
    hedonic_factors={"surface": 1.0, "condition": 0.82, "antiquity": 0.84,
                     "floor_elevator": 0.82, "energy": 0.95, "orientation": 1.0},
    cadastral_reference="0244802VK4704C",
    cadastral_year=1914,
)
print(json.dumps(result, indent=2, ensure_ascii=False))

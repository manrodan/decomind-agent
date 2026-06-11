"""
Valuation API — endpoint REST del motor de valoración (GCP / Cloud Run).

Expone `run_valuation` como JSON estable para que Decomind (Azure) lo consuma
por HTTP. Autenticación simple por API key (header X-Api-Key), suficiente para
integración server-to-server entre clouds.

Endpoints:
  GET  /health    -> {status, sources}
  POST /valuate   -> valoración completa (requiere X-Api-Key)

Env vars:
  VALUATION_API_KEY  -> clave esperada en el header X-Api-Key (obligatoria en prod)
  PORT               -> puerto (Cloud Run lo inyecta)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

# Flexible import: package layout in local dev, flat layout in the container.
try:
    from valuation_api.engine import run_valuation
except ImportError:  # container: app.py and engine.py at /app root
    from engine import run_valuation

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("valuation.api")

API_KEY = os.environ.get("VALUATION_API_KEY", "").strip()

app = FastAPI(
    title="Decomind Valuation API",
    description="Deterministic Spanish real-estate valuation (Notariado + MITMA "
                "+ Catastro + hedonic model). No LLM.",
    version="1.0.0",
)


class RoomIn(BaseModel):
    kind: str
    area_sqm: float = 0


class ValuationRequest(BaseModel):
    address: str = Field(..., description="Calle y número")
    locality: str = ""
    province: str = ""
    postal_code: str = ""
    surface_m2: float = Field(..., gt=0)
    condition: str = "buen_estado"
    year_built: int = 0
    floor: int | None = None
    has_elevator: bool = True
    is_attic: bool = False
    energy_rating: str = ""
    exterior: bool = True
    rooms: list[RoomIn] | None = None
    renovation_tier: str = "standard"
    include_renovation: bool = True


def _check_key(x_api_key: str | None) -> None:
    # Si VALUATION_API_KEY no está configurada, no se exige (dev local).
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid or missing X-Api-Key")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "valuation-api",
        "auth_required": bool(API_KEY),
        "sources": ["notariado", "mitma", "catastro", "geocoding"],
    }


@app.post("/valuate")
async def valuate(
    req: ValuationRequest,
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
) -> dict[str, Any]:
    _check_key(x_api_key)
    logger.info("Valuation request: %s (%s m2, %s)",
                req.address, req.surface_m2, req.condition)
    try:
        result = run_valuation(
            address=req.address,
            locality=req.locality,
            province=req.province,
            postal_code=req.postal_code,
            surface_m2=req.surface_m2,
            condition=req.condition,
            year_built=req.year_built,
            floor=req.floor,
            has_elevator=req.has_elevator,
            is_attic=req.is_attic,
            energy_rating=req.energy_rating,
            exterior=req.exterior,
            rooms=[r.model_dump() for r in req.rooms] if req.rooms else None,
            renovation_tier=req.renovation_tier,
            include_renovation=req.include_renovation,
        )
        return result
    except Exception as exc:
        logger.exception("Valuation failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

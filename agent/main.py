"""
Agente ADK con MCP servers: geocoding + market-research.

Día 4: el agente ya puede ejecutar el pipeline básico de un dossier:
  1. geocode_address — dirección → lat/lon + barrio/distrito
  2. find_comparables — comparables en la zona
  3. estimate_market_value — valoración del inmueble
  4. compute_renovation_roi — ROI si hay reforma planteada

Smoke test: dirección + superficie + estado → resumen para el agente inmobiliario.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
    StdioServerParameters,
)
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.genai import types

load_dotenv()

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west1")
MODEL = os.environ.get("AGENT_MODEL", "gemini-2.5-flash")

REPO_ROOT = Path(__file__).resolve().parent.parent


def _stdio_toolset(module: str) -> McpToolset:
    """Crea un McpToolset que spawnea un MCP server local por stdio."""
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", module],
                cwd=str(REPO_ROOT),
            ),
        ),
    )


geocoding_tools = _stdio_toolset("mcp_servers.geocoding.server")
market_research_tools = _stdio_toolset("mcp_servers.market_research.server")
renovation_tools = _stdio_toolset("mcp_servers.renovation.server")


root_agent = Agent(
    name="decomind_dossier_agent",
    model=MODEL,
    description=(
        "Agente inmobiliario que prepara dossiers de venta y propuestas de reforma "
        "para propiedades en España, usando datos reales de zona, comparables y "
        "presupuestos de reforma por capítulos."
    ),
    instruction=(
        "Eres un asistente experto del agente inmobiliario español. Preparas "
        "valoraciones y propuestas de reforma en pasos auditables, llamando "
        "a las tools en este orden cuando proceda:\n"
        "\n"
        "FASE 1 — Zona y valor actual\n"
        "  1) `geocode_address` — dirección → devuelve lat, lon, municipality, "
        "     province, city_district, neighbourhood. Quédate con esos campos.\n"
        "  2) `find_comparables` — debes pasar SIEMPRE:\n"
        "       lat, lon (del paso 1)\n"
        "       province = lo que devolvió geocoding como `province`\n"
        "       municipality = lo que devolvió geocoding como `municipality`\n"
        "       district = lo que devolvió geocoding como `city_district`\n"
        "     Pasar `municipality` activa el lookup en datos MITMA oficiales.\n"
        "  3) `estimate_market_value` con condition='a_reformar' (si está a reformar)\n"
        "     o el estado real → VALOR ACTUAL. Cita el `data_source` devuelto por\n"
        "     `find_comparables` (mitma_municipal / curated_province / mitma_province /\n"
        "     fallback) — es la trazabilidad oficial del dato.\n"
        "\n"
        "FASE 2 — Propuesta de reforma (solo si el usuario menciona reformar)\n"
        "  4) `estimate_renovation_plan` con las estancias del inmueble y un tier.\n"
        "     Si el usuario no especifica tier, prueba 'standard'.\n"
        "     Si el usuario no detalla estancias, pide lista o asume una "
        "     distribución razonable según los m² totales (ej. 90m² => salón, "
        "     cocina, baño, 2 dormitorios, pasillo) y dilo explícitamente.\n"
        "  5) `estimate_market_value` otra vez con condition='buen_estado' → "
        "     VALOR POST-REFORMA.\n"
        "  6) `compute_renovation_roi` usando totals.integral del paso 4 como "
        "     investment_eur, valor actual del paso 3, y valor post-reforma del "
        "     paso 5.\n"
        "\n"
        "REGLAS\n"
        "- No inventes presupuesto. Si pidieras inversión, usa SIEMPRE el output "
        "  de `estimate_renovation_plan`, nunca un número del usuario.\n"
        "- Si el usuario aporta un presupuesto, contrástalo con totals.integral y "
        "  comenta la diferencia.\n"
        "- Resume en español, con tablas markdown para presupuesto y ROI.\n"
        "- Indica el `source: synthetic-mvp` de los comparables y reproduce el "
        "  `disclaimer` del presupuesto al final.\n"
        "- Veredicto final de 2-3 líneas para el propietario."
    ),
    tools=[geocoding_tools, market_research_tools, renovation_tools],
)


async def smoke() -> None:
    runner = InMemoryRunner(agent=root_agent, app_name="decomind-agent")
    session = await runner.session_service.create_session(
        app_name="decomind-agent", user_id="local-dev"
    )

    prompt = (
        "Prepara un dossier de valoración + propuesta de reforma para este piso:\n"
        "- Dirección: Calle Mayor 5, Madrid, CP 28013\n"
        "- Superficie: 95 m²\n"
        "- Estado actual: a_reformar\n"
        "- Año construcción: 1965\n"
        "- Estancias: salón 24m², cocina 11m², baño 5m², dormitorio principal "
        "  16m², dormitorio secundario 12m², pasillo 7m²\n"
        "- Tier de reforma deseado: standard\n"
        "\n"
        "Calcula valor actual, presupuesto de reforma desglosado, valor post-reforma "
        "y ROI. Da un veredicto accionable."
    )

    print(f"\n[user]\n{prompt}\n")
    print(f"[agent: {MODEL} @ {PROJECT}/{LOCATION}]\n")

    content = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])

    async for event in runner.run_async(
        user_id="local-dev",
        session_id=session.id,
        new_message=content,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(part.text, end="", flush=True)
                elif part.function_call:
                    args = dict(part.function_call.args)
                    print(f"\n[tool call] {part.function_call.name}({args})")
                elif part.function_response:
                    # acorta el dump si es muy largo
                    resp = part.function_response.response
                    txt = str(resp)
                    if len(txt) > 500:
                        txt = txt[:500] + " ...(truncated)"
                    print(f"[tool response] {txt}")
    print()


if __name__ == "__main__":
    asyncio.run(smoke())

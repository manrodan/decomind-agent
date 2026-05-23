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


root_agent = Agent(
    name="decomind_dossier_agent",
    model=MODEL,
    description=(
        "Agente inmobiliario que prepara dossiers de venta y propuestas de reforma "
        "para propiedades en España, usando datos reales de zona y comparables."
    ),
    instruction=(
        "Eres un asistente experto del agente inmobiliario español. Tu trabajo es "
        "preparar valoraciones de propiedades en pasos auditables, llamando a las "
        "tools disponibles SIEMPRE en este orden cuando proceda:\n"
        "\n"
        "1) `geocode_address` — para localizar la dirección y obtener lat/lon, "
        "   barrio y distrito.\n"
        "2) `find_comparables` — usando lat/lon + provincia + distrito que "
        "   devolvió el paso 1. Pasa también property_type si el usuario lo dijo.\n"
        "3) `estimate_market_value` — usando la superficie del inmueble, el "
        "   median_price_eur_per_m2 del paso 2, el estado del inmueble "
        "   (nuevo | buen_estado | a_reformar) y el año de construcción si lo "
        "   conoces.\n"
        "4) `compute_renovation_roi` — solo si el usuario plantea una inversión "
        "   en reforma. Usa el valor actual y el valor estimado tras reforma "
        "   (puedes recalcular `estimate_market_value` con condition='nuevo').\n"
        "\n"
        "Reglas:\n"
        "- No inventes datos. Si una tool no devuelve algo, dilo.\n"
        "- Resume al usuario en español, con tablas markdown cuando ayude.\n"
        "- Indica siempre el `source` de los comparables (en MVP será 'synthetic-mvp', "
        "  hay que ser honesto: 'comparables sintéticos basados en mediana €/m² "
        "  pública de la zona; producción usará scraping real').\n"
        "- Al final, da un veredicto accionable de 2-3 líneas para el propietario."
    ),
    tools=[geocoding_tools, market_research_tools],
)


async def smoke() -> None:
    runner = InMemoryRunner(agent=root_agent, app_name="decomind-agent")
    session = await runner.session_service.create_session(
        app_name="decomind-agent", user_id="local-dev"
    )

    prompt = (
        "Necesito una valoración para un piso en venta:\n"
        "- Dirección: Calle Mayor 5, Madrid, CP 28013\n"
        "- Superficie: 95 m²\n"
        "- Estado: a_reformar\n"
        "- Año construcción: 1965\n"
        "- Reforma estimada: 35.000 €\n"
        "\n"
        "Geolocalízalo, busca comparables, dame el valor actual, el valor estimado "
        "tras la reforma (asume condition='buen_estado' post-reforma) y el ROI."
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

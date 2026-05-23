"""
Agente ADK con su primer tool MCP: geocoding.

Día 3: el agente recibe una dirección española y debe geolocalizarla llamando
al MCP server `geocoding` (Nominatim/OSM).

Smoke test: pedir la zona/barrio de una dirección conocida.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
    StdioServerParameters,
)
from google.genai import types

load_dotenv()

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west1")
MODEL = os.environ.get("AGENT_MODEL", "gemini-2.5-flash")

REPO_ROOT = Path(__file__).resolve().parent.parent

geocoding_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,  # mismo intérprete del venv
            args=["-m", "mcp_servers.geocoding.server"],
            cwd=str(REPO_ROOT),
        ),
    ),
)


root_agent = Agent(
    name="decomind_dossier_agent",
    model=MODEL,
    description=(
        "Agente inmobiliario que prepara dossiers de venta de propiedades en España. "
        "Día 3: tiene acceso a una herramienta de geocoding."
    ),
    instruction=(
        "Eres un agente inmobiliario asistente. Cuando el usuario te dé una dirección, "
        "usa la tool `geocode_address` para localizarla. Devuelve un resumen breve con: "
        "barrio o distrito, coordenadas, y dirección normalizada. "
        "Si la geocodificación falla, indícalo claramente. "
        "No inventes datos: si la tool no devuelve un campo, dilo."
    ),
    tools=[geocoding_toolset],
)


async def smoke() -> None:
    runner = InMemoryRunner(agent=root_agent, app_name="decomind-agent")
    session = await runner.session_service.create_session(
        app_name="decomind-agent", user_id="local-dev"
    )

    prompts = [
        "Geolocaliza esta dirección: Calle Mayor 5, Madrid, código postal 28013. "
        "Dime barrio, distrito y coordenadas.",
    ]

    for prompt in prompts:
        print(f"\n[user] {prompt}\n")
        print(f"[agent: {MODEL} @ {PROJECT}/{LOCATION}]")

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
                        print(
                            f"\n[tool call] {part.function_call.name}"
                            f"({dict(part.function_call.args)})"
                        )
                    elif part.function_response:
                        resp = part.function_response.response
                        print(f"[tool response] {resp}")
        print()


if __name__ == "__main__":
    asyncio.run(smoke())

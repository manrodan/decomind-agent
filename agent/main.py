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
import logging
import os
import subprocess
import sys
from functools import lru_cache
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

# Logging visible en stdout (Reasoning Engine lo captura como Cloud Logging).
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("decomind.agent")

# Carga el .env. En local dev: .env del repo root o del cwd.
# En runtime cloud (Agent Engine): el .env empaquetado junto a este fichero.
# Llamamos a load_dotenv DOS veces con paths explícitos para cubrir ambos casos.
_MODULE_ENV = Path(__file__).resolve().parent / ".env"
if _MODULE_ENV.exists():
    load_dotenv(_MODULE_ENV)
    logger.info("Loaded env from %s", _MODULE_ENV)
load_dotenv()  # default search — cwd y parents (dev local)

# Defaults seguros para que el módulo sea importable sin .env (necesario para
# que `adk deploy` pueda hacer packaging). En runtime real las env vars deben
# estar definidas (Agent Engine recibe --set-env-vars; Cloud Run idem).
PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "decomind-agent-challenge")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west1")
MODEL = os.environ.get("AGENT_MODEL", "gemini-2.5-flash")

# Service account a impersonar para obtener ID tokens hacia Cloud Run (HTTP MCP).
# Solo se usa en local dev. En GCP runtime (Agent Engine, Cloud Run) se usa la
# identidad propia del runtime via metadata server, sin impersonación.
MCP_AUTH_SA = os.environ.get(
    "MCP_AUTH_SERVICE_ACCOUNT",
    f"decomind-agent-dev@{PROJECT}.iam.gserviceaccount.com",
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ── HTTP MCP auth helper ──────────────────────────────────────────────────
#
# El agente puede correr en dos contextos:
#
#   1) LOCAL DEV — user creds via gcloud ADC, sin permiso de auto-emitir ID
#      tokens con audience. Necesita impersonar la SA decomind-agent-dev
#      ejecutando `gcloud auth print-identity-token`.
#
#   2) GCP RUNTIME (Cloud Run / Agent Engine / GCE / GKE) — metadata server
#      disponible. La SA del runtime puede solicitar ID tokens directamente
#      sin impersonación si tiene `run.invoker` sobre el target.
#
# Detectamos contexto al primer intento: probamos metadata server, si falla
# caemos a gcloud subprocess.


def _fetch_via_metadata(audience: str) -> str | None:
    """Intenta obtener un ID token vía metadata server (GCP runtime)."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import id_token
        token = id_token.fetch_id_token(Request(), audience)
        logger.info("Metadata server returned ID token for %s (len=%d)",
                    audience, len(token) if token else 0)
        return token
    except Exception as exc:
        logger.warning("Metadata server fetch failed for %s: %s", audience, exc)
        return None


def _fetch_via_gcloud(audience: str) -> str:
    """Fallback: gcloud impersonation (dev local con user creds)."""
    logger.info("Trying gcloud impersonation for %s", audience)
    cmd = [
        "gcloud", "auth", "print-identity-token",
        f"--impersonate-service-account={MCP_AUTH_SA}",
        f"--audiences={audience}",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True,
            shell=(os.name == "nt"),
        )
        return result.stdout.strip()
    except FileNotFoundError:
        logger.error("gcloud not available in this environment (expected in cloud runtime)")
        raise
    except subprocess.CalledProcessError as exc:
        logger.error("gcloud failed: %s", exc.stderr)
        raise


@lru_cache(maxsize=8)
def _get_id_token(audience: str) -> str:
    """Devuelve OIDC ID token para `audience`. Cacheado por proceso (~1h)."""
    token = _fetch_via_metadata(audience)
    if token:
        return token
    return _fetch_via_gcloud(audience)


# ── Toolsets — selección stdio (local) vs HTTP (Cloud Run) ────────────────

def _stdio_toolset(module: str) -> McpToolset:
    """Spawnea un MCP server local por stdio. Para dev local."""
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", module],
                cwd=str(REPO_ROOT),
            ),
        ),
    )


def _http_toolset(url: str) -> McpToolset:
    """Conecta a un MCP server vía HTTP (Cloud Run). Token estático resuelto
    al cargar el módulo. En Agent Engine el contenedor vive ~1h por sesión,
    el token (también ~1h) suele cubrir; para sesiones más largas se reinicia.
    """
    # Importación tardía — la clase puede llamarse distinta según versión ADK.
    try:
        from google.adk.tools.mcp_tool.mcp_session_manager import (
            StreamableHTTPConnectionParams,
        )
    except ImportError:
        from google.adk.tools.mcp_tool.mcp_session_manager import (  # type: ignore
            StreamableHttpConnectionParams as StreamableHTTPConnectionParams,
        )

    full_url = f"{url}/mcp"
    logger.info("Building HTTP MCP toolset for %s", full_url)
    try:
        token = _get_id_token(url)
        logger.info("HTTP MCP toolset auth resolved for %s (token len=%d)",
                    full_url, len(token))
    except Exception as exc:
        logger.error("HTTP MCP toolset auth FAILED for %s: %s", full_url, exc)
        raise

    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=full_url,
            headers={"Authorization": f"Bearer {token}"},
        ),
    )


def _toolset(env_url_var: str, stdio_module: str) -> McpToolset:
    """Devuelve toolset HTTP si la env var URL está definida, si no stdio."""
    url = os.environ.get(env_url_var, "").strip().rstrip("/")
    if url:
        logger.info("Toolset %s -> HTTP %s", env_url_var, url)
        return _http_toolset(url)
    logger.info("Toolset %s -> stdio (%s)", env_url_var, stdio_module)
    return _stdio_toolset(stdio_module)


logger.info(
    "Initializing Decomind Agent — project=%s location=%s model=%s",
    PROJECT, LOCATION, MODEL,
)
logger.info(
    "MCP env vars present: geocoding=%s market=%s reno=%s pdf=%s",
    bool(os.environ.get("MCP_GEOCODING_URL")),
    bool(os.environ.get("MCP_MARKET_RESEARCH_URL")),
    bool(os.environ.get("MCP_RENOVATION_URL")),
    bool(os.environ.get("MCP_DOSSIER_PDF_URL")),
)

geocoding_tools       = _toolset("MCP_GEOCODING_URL",       "mcp_servers.geocoding.server")
catastro_tools        = _toolset("MCP_CATASTRO_URL",        "mcp_servers.catastro.server")
notariado_tools       = _toolset("MCP_NOTARIADO_URL",       "mcp_servers.notariado.server")
market_research_tools = _toolset("MCP_MARKET_RESEARCH_URL", "mcp_servers.market_research.server")
renovation_tools      = _toolset("MCP_RENOVATION_URL",      "mcp_servers.renovation.server")
dossier_pdf_tools     = _toolset("MCP_DOSSIER_PDF_URL",     "mcp_servers.dossier_pdf.server")


root_agent = Agent(
    name="decomind_dossier_agent",
    model=MODEL,
    # Temperatura 0 → máxima reproducibilidad. Una valoración inmobiliaria debe
    # ser consistente: el mismo inmueble debe dar el mismo valor en cada
    # ejecución (web, playground, API). La variabilidad del LLM en la
    # orquestación no es aceptable para un AVM.
    generate_content_config=types.GenerateContentConfig(temperature=0.0),
    description=(
        "Agente inmobiliario que prepara dossiers de venta y propuestas de reforma "
        "para propiedades en España, usando datos reales de zona, comparables y "
        "presupuestos de reforma por capítulos."
    ),
    instruction=(
        "Eres un asistente experto del agente inmobiliario español. Preparas "
        "valoraciones REPRODUCIBLES: el mismo inmueble debe dar siempre el mismo "
        "resultado. Cuando un dato no se especifica, aplica SIEMPRE estos "
        "supuestos por defecto (no improvises):\n"
        "  - Estado: si no se indica, usa 'buen_estado'.\n"
        "  - Tier de reforma: si no se indica, usa 'standard'.\n"
        "  - Planta/ascensor/energía/exterior/orientación/habitaciones/baños/"
        "    extras: si no se mencionan, NO los pases (el modelo usa neutro y "
        "    los lista en unknown_inputs). No los inventes.\n"
        "  - Si el usuario pega características de un anuncio (Idealista), "
        "    llama primero a `parse_property_features` y usa sus `fields` como "
        "    inputs hedónicos; lo de `unmatched` ignóralo.\n"
        "  - Estancias para reforma: si no se detallan, deríbalas de la superficie "
        "    con esta regla fija: salón=25%, cocina=12%, cada baño=6%, "
        "    dormitorios=resto repartido, pasillo=8%. Indica que son estimadas.\n"
        "Preparas el dossier en pasos auditables, llamando "
        "a las tools en este orden cuando proceda:\n"
        "\n"
        "FASE 1 — Zona y valor actual\n"
        "  1) `geocode_address` — dirección → devuelve lat, lon, municipality, "
        "     province, city_district, neighbourhood. Quédate con esos campos.\n"
        "  2) `catastro_lookup` — pasa lat, lon del paso 1. Devuelve datos OFICIALES\n"
        "     del Catastro: year_built (año de construcción REAL), primary_use,\n"
        "     cadastral_reference, address (confirmada). USA SIEMPRE este year_built\n"
        "     en lugar del que diga el usuario — es el oficial. Si el usuario no\n"
        "     dio año, este es la fuente. Si catastro_lookup falla (found=false),\n"
        "     continúa con el año del usuario y dilo.\n"
        "  3) `notariado_price` — CÓDIGO POSTAL: usa SIEMPRE el código postal que\n"
        "     dio el usuario en su mensaje (literal). Solo si el usuario NO indicó\n"
        "     código postal, usa el `postcode` del geocoding. No infieras ni\n"
        "     cambies el CP entre ejecuciones — debe ser determinista. Pasa también\n"
        "     municipality y province del geocoding.\n"
        "     Devuelve el PRECIO REAL de compraventa ante notario\n"
        "     (price_eur_per_m2) + num_transactions + level. ES LA FUENTE PRIMARIA\n"
        "     DE PRECIO (transacciones reales). Cítalo con el nº de transacciones\n"
        "     y el nivel geográfico. NOTA: ciudades como Marbella tienen varios CP\n"
        "     con precios muy distintos; por eso el CP debe ser el del usuario.\n"
        "  4) `find_comparables` — pasa lat, lon, province, municipality, district.\n"
        "     Devuelve la mediana MITMA (valor TASADO) — la usamos como SEGUNDA\n"
        "     fuente de contraste (tasación vs transacción real). Inmuebles\n"
        "     comparables de la zona.\n"
        "  5) `estimate_market_value` → VALOR ACTUAL. Para median_price_eur_per_m2\n"
        "     usa SIEMPRE el price_eur_per_m2 del NOTARIADO (paso 3, precio real),\n"
        "     NO el de MITMA. Pasa además todos los datos hedónicos:\n"
        "       surface_m2, condition, year_built (del Catastro, paso 2),\n"
        "       floor, has_elevator (1/0/-1), is_attic, energy_rating,\n"
        "       exterior (1/0/-1), orientation, bedrooms, bathrooms,\n"
        "       has_terrace, has_garage, has_storage_room, has_pool\n"
        "       (los que el usuario haya mencionado o el parser haya extraído).\n"
        "     Cita el `combined_factor` hedónico.\n"
        "\n"
        "  TRIANGULACIÓN DE FUENTES (guardrail de calidad):\n"
        "  Llama a `check_source_agreement(notariado_price_eur_per_m2,\n"
        "  mitma_price_eur_per_m2)`. Devuelve convergence_pct, agreement y\n"
        "  requires_review. Reporta SIEMPRE las dos fuentes en paralelo:\n"
        "    - Notariado (precio REAL de transacción): X €/m² · N ventas\n"
        "    - MITMA (valor tasado de referencia): Y €/m²\n"
        "  Si requires_review=true, AVISA explícitamente al usuario de que las\n"
        "  fuentes divergen y conviene revisión humana antes de fijar precio.\n"
        "  Si `estimate_market_value` devuelve warnings o requires_review,\n"
        "  trasládalos también al usuario (no des un número a ciegas).\n"
        "\n"
        "FASE 2 — Propuesta de reforma (solo si el usuario menciona reformar)\n"
        "  6) `estimate_renovation_plan` con las estancias del inmueble y un tier.\n"
        "     Si el usuario no especifica tier, prueba 'standard'.\n"
        "     Si el usuario no detalla estancias, pide lista o asume una "
        "     distribución razonable según los m² totales (ej. 90m² => salón, "
        "     cocina, baño, 2 dormitorios, pasillo) y dilo explícitamente.\n"
        "  7) `estimate_market_value` otra vez con condition='buen_estado' (manteniendo\n"
        "     el precio Notariado como base y el resto de factores hedónicos:\n"
        "     floor, ascensor, energía mejorada tras reforma, etc.) → VALOR POST-REFORMA.\n"
        "  8) `compute_renovation_roi` usando totals.integral del paso 6 como "
        "     investment_eur, valor actual del paso 5, y valor post-reforma del "
        "     paso 7.\n"
        "\n"
        "FASE 3 — Empaquetado en PDF (último paso, solo si el usuario lo pide)\n"
        "  9) DEBES INVOCAR la tool `render_dossier_pdf`. No describas, no muestres\n"
        "     código Python, no listes parámetros — LLAMA a la tool y espera su\n"
        "     respuesta. Su respuesta contiene la URL del PDF generado.\n"
        "     Parámetros obligatorios:\n"
        "       - property_address, property_municipality, property_district,\n"
        "         property_surface_m2, property_year_built, property_condition\n"
        "       - median_price_eur_per_m2 = precio del NOTARIADO (paso 3)\n"
        "       - data_source: pon 'notariado_<level>' (ej 'notariado_codigo_postal')\n"
        "       - notariado_price_m2, notariado_transactions, notariado_level (paso 3)\n"
        "       - mitma_price_m2 = mediana de find_comparables (paso 4, contraste)\n"
        "       - current_value_eur (del paso 5)\n"
        "       - post_reno_value_eur (del paso 7)\n"
        "       - renovation_total_integral_eur (del paso 6: totals.integral)\n"
        "       - renovation_tier (del paso 6)\n"
        "       - by_room (EXACTAMENTE el array by_room del paso 6, sin tocar)\n"
        "       - hedonic_factors (el dict 'factors' del paso 5)\n"
        "       - cadastral_reference, cadastral_year (del paso 2)\n"
        "       - roi_net_gain_eur, roi_payback_ratio, roi_recommendation\n"
        "         (todos del paso 8)\n"
        "       - agent_verdict (2-3 frases tuyas, EN INGLÉS)\n"
        "       - property_features (lista de strings cortos en INGLÉS, ej:\n"
        "         'Built in 1965', 'No elevator', 'Energy rating E')\n"
        "     Tras la tool, incluye en tu respuesta un enlace markdown de descarga\n"
        "     usando EXACTAMENTE el valor del campo url del response (es una URL\n"
        "     que empieza por https://storage.googleapis.com/). Cópiala literal,\n"
        "     carácter por carácter. NUNCA escribas un placeholder con llaves ni\n"
        "     inventes la URL: usa la real y completa del response.\n"
        "     property_features: lista de strings cortos con características\n"
        "     adicionales que el usuario haya mencionado. **EN INGLÉS** porque\n"
        "     el PDF final está en inglés. Ej: 'No elevator', 'Energy rating E',\n"
        "     'Sea view', '2 bedrooms', '1 bathroom', 'Balcony', 'Standard build "
        "     quality'. Traduce lo que el usuario diga. Si no mencionó nada,\n"
        "     pasa lista vacía [].\n"
        "\n"
        "IMPORTANTE — IDIOMA DEL PDF\n"
        "El PDF entregable está en INGLÉS (jurado internacional). Por tanto:\n"
        "  - El parámetro `agent_verdict` debe estar en INGLÉS (2-3 frases).\n"
        "  - Los `property_features` deben estar en INGLÉS.\n"
        "  - Lo que respondas al usuario en chat puede ser en español (como te\n"
        "    haya hablado), pero el contenido que va al PDF siempre en inglés.\n"
        "\n"
        "REGLAS\n"
        "- No inventes presupuesto. Si pidieras inversión, usa SIEMPRE el output "
        "  de `estimate_renovation_plan`, nunca un número del usuario.\n"
        "- Si el usuario aporta un presupuesto, contrástalo con totals.integral y "
        "  comenta la diferencia.\n"
        "- Resume en español, con tablas markdown para presupuesto y ROI.\n"
        "- Indica el `source: synthetic-mvp` de los comparables y reproduce el "
        "  `disclaimer` del presupuesto al final.\n"
        "- Veredicto final de 2-3 líneas para el propietario.\n"
        "- Si generas el PDF, devuelve al usuario la ruta local del archivo."
    ),
    tools=[
        geocoding_tools,
        catastro_tools,
        notariado_tools,
        market_research_tools,
        renovation_tools,
        dossier_pdf_tools,
    ],
)


async def smoke() -> None:
    runner = InMemoryRunner(agent=root_agent, app_name="decomind-agent")
    session = await runner.session_service.create_session(
        app_name="decomind-agent", user_id="local-dev"
    )

    prompt = (
        "Prepara un dossier completo para entregar al propietario de este piso:\n"
        "- Dirección: Calle Mayor 5, Madrid, CP 28013\n"
        "- Superficie: 95 m²\n"
        "- Estado actual: a_reformar\n"
        "- Año construcción: 1965\n"
        "- Estancias: salón 24m², cocina 11m², baño 5m², dormitorio principal "
        "  16m², dormitorio secundario 12m², pasillo 7m²\n"
        "- Tier de reforma deseado: standard\n"
        "\n"
        "Ejecuta el pipeline completo (zona, comparables, valoración, presupuesto, "
        "ROI) y AL FINAL llama a `render_dossier_pdf` con todos los datos para "
        "generar el PDF entregable. Dame la ruta del archivo generado."
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

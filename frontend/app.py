"""
Decomind Agent Web UI — backend (direct ADK).

FastAPI app que sirve la interfaz HTML y un endpoint `/chat` que ejecuta el
agente ADK directamente (sin pasar por Agent Engine) y streamea eventos al
navegador vía Server-Sent Events.

Por qué directo y no via Agent Engine REST:
  El playground de Vertex AI Agent Engine activa una variante del modelo que
  ocasionalmente devuelve sintaxis "code-interpreter" (print(default_api.X(...)))
  en lugar de function_call estructurados, lo que rompe la ejecución de tools.
  El Runner local de ADK (mismo que usamos en scripts/demo_set) es estable y
  dispara siempre function calls correctamente.

  Agent Engine sigue desplegado (Reasoning Engine 8355329596958179328) como
  asset arquitectónico para la submission del challenge.

Auth: corre como SA decomind-agent-dev en Cloud Run (vía metadata server),
o como user ADC en local. La SA tiene run.invoker en los 4 MCPs.

Env vars necesarias:
    GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION
    MCP_GEOCODING_URL, MCP_MARKET_RESEARCH_URL, MCP_RENOVATION_URL, MCP_DOSSIER_PDF_URL
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("decomind.ui")

# Permite que `agent` y `mcp_servers` se encuentren en imports.
# En Cloud Run, los copiamos junto a app.py (mismo cwd /app).
# En local, los buscamos en la raíz del repo (parent dir de frontend/).
REPO_ROOT = Path(__file__).resolve().parent.parent
for candidate in (Path(__file__).resolve().parent, REPO_ROOT):
    if (candidate / "agent" / "main.py").exists():
        sys.path.insert(0, str(candidate))
        break

# Import del agente (resuelve toolsets HTTP usando MCP_*_URL env vars).
from agent.main import root_agent  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "decomind-agent-challenge")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west1")

logger.info("Booting Decomind UI — project=%s location=%s", PROJECT, LOCATION)
logger.info("Agent name=%s", root_agent.name)

_runner = InMemoryRunner(agent=root_agent, app_name="decomind-agent-ui")

app = FastAPI(title="Decomind Agent UI")

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ChatRequest(BaseModel):
    message: str
    user_id: str = "web-user"


def _sse(event_type: str, payload: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _serialize_args(args) -> dict:
    """Convierte function_call.args a un dict JSON-friendly."""
    try:
        if hasattr(args, "items"):
            return {k: _serialize_value(v) for k, v in args.items()}
        return {}
    except Exception:
        return {}


def _serialize_value(v):
    if isinstance(v, dict):
        return {k: _serialize_value(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_serialize_value(x) for x in v]
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)


async def _stream_agent(message: str, user_id: str) -> AsyncGenerator[str, None]:
    """Ejecuta el agente ADK y emite eventos SSE."""
    try:
        logger.info("New chat — user=%s len=%d", user_id, len(message))
        session = await _runner.session_service.create_session(
            app_name="decomind-agent-ui", user_id=user_id,
        )
        session_id = session.id
        yield _sse("session", {"session_id": session_id, "user_id": user_id})

        content = types.Content(role="user", parts=[types.Part.from_text(text=message)])

        ev_count = 0
        async for event in _runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            ev_count += 1
            if not event.content or not event.content.parts:
                continue
            for part in event.content.parts:
                if getattr(part, "function_call", None):
                    fc = part.function_call
                    yield _sse("tool_call", {
                        "name": fc.name,
                        "args": _serialize_args(fc.args),
                    })
                elif getattr(part, "function_response", None):
                    fr = part.function_response
                    resp = fr.response or {}
                    # MCP devuelve {"structuredContent": {...}, "content": [...]}.
                    # Preferimos structuredContent (el dict puro).
                    if isinstance(resp, dict) and "structuredContent" in resp:
                        resp = resp["structuredContent"]
                    yield _sse("tool_response", {
                        "name": fr.name,
                        "response": _serialize_value(resp),
                    })
                elif getattr(part, "text", None):
                    yield _sse("text", {"text": part.text})

        logger.info("Stream done — %d events processed", ev_count)
        yield _sse("done", {})
    except Exception as exc:
        logger.exception("Agent stream failed: %s", exc)
        yield _sse("error", {"message": str(exc)})


@app.post("/chat")
async def chat(req: ChatRequest):
    return StreamingResponse(
        _stream_agent(req.message, req.user_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "project": PROJECT,
        "agent": root_agent.name,
        "mode": "direct-adk",
    }


@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")

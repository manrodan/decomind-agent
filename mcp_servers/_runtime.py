"""
Runtime helper para los MCP servers.

Permite que el mismo `server.py` corra tanto en local (stdio, para dev y para
spawn-by-agent) como en Cloud Run (HTTP en $PORT, convención GCP).

Selección:
  - MCP_TRANSPORT=stdio (default) → stdio
  - MCP_TRANSPORT=http             → streamable-http en 0.0.0.0:$PORT (default 8080)
"""

from __future__ import annotations

import logging
import os
from typing import Any


def run_server(mcp: Any) -> None:
    """Lanza un FastMCP en el transport correcto según env vars.

    En modo HTTP, no usamos `mcp.run(transport='streamable-http')` directamente
    porque uvicorn arranca SIN `proxy_headers`, y al estar detrás del frontend
    TLS de Cloud Run los redirects salen con `http://...` (rotos) y los Hosts
    se ven como inválidos. Lanzamos uvicorn nosotros mismos con la config
    correcta para entornos proxified.
    """
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport == "http":
        port = int(os.getenv("PORT", "8080"))
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("mcp.runtime").info(
            "Starting MCP server '%s' on HTTP 0.0.0.0:%s",
            getattr(mcp, "name", "?"), port,
        )

        # Desactivar DNS rebinding protection del MCP SDK: en Cloud Run + IAM
        # los hosts válidos son los de Cloud Run (cambian por servicio), y solo
        # llegan requests autenticados. La protección DNS-rebinding está
        # pensada para servidores MCP local sin auth — no aplica aquí.
        try:
            from mcp.server.transport_security import TransportSecuritySettings
            mcp.settings.transport_security = TransportSecuritySettings(
                enable_dns_rebinding_protection=False,
            )
        except Exception as exc:
            logging.getLogger("mcp.runtime").warning(
                "No se pudo desactivar DNS rebinding protection: %s", exc,
            )

        import uvicorn
        app = mcp.streamable_http_app()
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            proxy_headers=True,       # respeta X-Forwarded-* de Cloud Run
            forwarded_allow_ips="*",  # confiamos en cualquier IP origen (Cloud Run proxy)
            log_level="info",
        )
    else:
        # stdio — dev local + spawn-by-agent. Sin logging a stdout (rompe protocolo).
        mcp.run(transport="stdio")

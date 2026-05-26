"""
Punto de entrada que espera `adk deploy agent_engine`.

ADK genera automáticamente un `agent_engine_app.py` con la línea:
    from .agent import root_agent

Tras el staging, los ficheros de `agent/` quedan planos en el temp folder,
así que `.agent` resuelve a este fichero (`agent.py`). Re-exportamos
`root_agent` desde `main.py` para que la única fuente de verdad siga ahí.
"""

from .main import root_agent

__all__ = ["root_agent"]

"""Decomind Agent — paquete del agente.

Reexportamos `root_agent` para que el entrypoint que genera `adk deploy
agent_engine` (que hace `from .agent import root_agent`) lo encuentre.
"""

from .main import root_agent

__all__ = ["root_agent"]

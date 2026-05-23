# Decomind Agent

Agente inmobiliario autónomo construido para el **Google for Startups AI Agents Challenge — Track 3 (Refactor)**.

Refactoriza el flujo de Dossier de Decomind (hoy en Azure Functions) a una arquitectura agéntica nativa GCP: **ADK + MCP + Vertex AI + Gemini Enterprise**, lista para Google Cloud Marketplace.

## Estado

- **Deadline submission:** 2026-06-05
- **Track:** 3 (Refactor)
- **Repo:** aislado — no comparte código ni infra con producción Decomind. Ver `docs/isolation-rules.md`.

## Quickstart

```powershell
# 1. Crear venv y activar
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instalar deps
pip install -e .

# 3. Copiar config
copy .env.example .env
# (editar .env con tu PROJECT y LOCATION reales)

# 4. Smoke test del agente
python -m agent.main
```

Si el smoke test imprime una respuesta del modelo, ADC + Vertex + Gemini están conectados.

## Estructura

```
agent/           Agente ADK (orquestador)
mcp-servers/     Servidores MCP (tools — días 3-6)
docs/            Plan, business case, reglas de aislamiento
```

## Docs

- `docs/day-by-day.md` — plan de 14 días
- `docs/business-case.md` — esqueleto del business case
- `docs/isolation-rules.md` — qué NO se toca de producción Decomind

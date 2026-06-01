# Decomind Agent 🏠

**Autonomous Spanish real-estate valuation agent** — turns an address into a
full valuation + renovation ROI dossier (PDF) in ~30 seconds, grounded in
**official Spanish open data**, not LLM guesses.

Built for the **Google for Startups AI Agents Challenge — Track 3 (Refactor)**:
the production Dossier of [Decomind](https://decomind.es) (Azure Functions)
refactored to a cloud-native agentic architecture on Google Cloud.

> 🔗 **Live demo:** https://decomind-agent-ui-ajrpcon4fq-ew.a.run.app
> *(type an address or pick an example, watch the 9 tool calls stream live, download the PDF)*

---

## What it does

Give it a property (address, surface, condition) and the agent autonomously:

1. **Geocodes** the address (OpenStreetMap)
2. Pulls **official cadastral data** — build year, use, reference (Catastro)
3. Fetches the **real transaction price** by postal code (Notariado — actual
   notarial sales, the gold standard)
4. Cross-checks with the **official appraisal value** (MITMA)
5. Computes the value with a **hedonic model** (6 calibrated factors)
6. Builds a **room-by-room renovation budget**
7. Calculates **ROI** and a verdict
8. Renders a branded **PDF** with charts

The LLM **orchestrates**; deterministic code **calculates**. Every number is
traceable to an official source and reproducible.

## Architecture

```
Browser → Cloud Run (web) → ADK agent (Gemini 3.5 Flash, Vertex AI)
                                   │ orchestrates
        ┌──────────┬──────────┬────┴─────┬───────────┬────────────┐
     geocoding  catastro  notariado  market-research renovation dossier-pdf   ← 6 MCP servers (Cloud Run)
        │          │          │          │            │            │
   OpenStreetMap  Catastro  Notariado   MITMA       rates      reportlab→GCS
```

13 federated Google Cloud services, no downloadable keys (OIDC + IAM).
Same agent also deployed on **Vertex AI Agent Engine** (managed, with playground).

## Stack

`ADK 2.1` · `Gemini 3.5 Flash (Vertex AI)` · `MCP` · `Cloud Run` ·
`Agent Engine` · `Cloud Build` · `Artifact Registry` · `IAM/OIDC` ·
`Cloud Storage` · `Cloud Trace` · `FastAPI` · `FastMCP`

## Data sources (official, free, no scraping)

| Source | What | Type |
|---|---|---|
| **Notariado** | Real sale prices by postal code | Actual transactions |
| **MITMA** | Appraisal value | Official reference |
| **Catastro** | Year, surface, use | Physical record |

## Quickstart (local)

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -e .
cp .env.example .env                            # set your GCP project
python -m agent.main                            # smoke test
```

Run the eval suite (against the real official APIs):

```bash
python -m evals.run        # 5 cases, 55 checks
```

## Repo layout

```
agent/          ADK agent (orchestrator) + instruction
mcp_servers/    6 MCP tool servers (geocoding, catastro, notariado,
                market_research [+ hedonic model], renovation, dossier_pdf)
evals/          Reproducible eval suite (100%, vs real APIs)
frontend/       FastAPI web UI with live tool-call streaming (SSE)
scripts/        Deploy scripts (Cloud Run, Agent Engine) + data parsers
docs/           Architecture, FAQ, console navigation, business case
```

## Documentation

- [`docs/arquitectura-resumen.md`](docs/arquitectura-resumen.md) — architecture, 3 levels (+ Azure equivalences)
- [`docs/system-overview.md`](docs/system-overview.md) — full technical overview + step-by-step example
- [`docs/faq-tecnico.md`](docs/faq-tecnico.md) — technical FAQ (why MCP, security, data, business)
- [`docs/google-cloud-manual.md`](docs/google-cloud-manual.md) — GCP services explained
- [`docs/business-case.md`](docs/business-case.md) — business case

## Production-readiness

- **Observability:** Cloud Logging + Trace; tool calls streamed live in the UI
- **Guardrails:** input/output validators, source-agreement check with
  human-review flag, deterministic config (`temperature=0`)
- **Evaluations:** reproducible suite (100%) against real official APIs
- **Security:** federated identity (OIDC), least-privilege IAM, zero keys
- **Cost:** scales to zero, ~€0.005 per dossier

## Known limitations (roadmap)

Individual real comparables (Idealista Data / property registry) are roadmap
M2 — current sources are official aggregates by area. Renders & shopping list
(present in V1) are a future add-on.

---

_Isolated from Decomind production (which runs on Azure). See
[`docs/isolation-rules.md`](docs/isolation-rules.md)._

# Decomind Agent — Visión técnica del sistema

> Doc personal para tener claro qué tenemos montado, cómo encaja cada pieza
> y por qué. Fuente única de verdad para el vídeo demo y la submission del
> Google for Startups AI Agents Challenge (Track 3 — Refactor).

---

## 1. Resumen en una frase

> Un agente inmobiliario autónomo que toma una dirección española + datos del
> inmueble, encadena 4 herramientas (geocodificación, comparables de mercado,
> presupuesto de reforma por capítulos y empaquetado PDF) y entrega al
> propietario un dossier de valoración con ROI en **~30 segundos** y por
> **céntimos** de coste — refactorización V2 del Dossier que Decomind ya
> tiene en producción (V1: Azure Functions, ~5-10 min, varios € por dossier).

---

## 2. Mapa visual del sistema

```
                     ┌──────────────────────────────┐
                     │      Navegador del usuario   │
                     │  (jurado, design partner)    │
                     └────────────────┬─────────────┘
                                      │ HTTPS
                                      ▼
       ┌──────────────────────────────────────────────────────┐
       │  Frontend Web UI                                     │
       │  Cloud Run · decomind-agent-ui                       │
       │  · FastAPI                                           │
       │  · UI chat dark con tool-calls en vivo (SSE)         │
       │  · Ejecuta el agente ADK DIRECTO (in-process)        │
       │  · Identidad: SA decomind-agent-dev                  │
       └────────────────┬─────────────────────────────────────┘
                        │  ADK Runner (in-process)
                        ▼
       ┌──────────────────────────────────────────────────────┐
       │  Decomind Agent (ADK 2.1)                            │
       │  · Modelo orquestador: gemini-2.5-flash @ Vertex AI │
       │  · Instrucción de 7 pasos (zona → reforma → ROI)     │
       │  · 4 toolsets MCP vía HTTP                           │
       └─┬────────────┬───────────┬──────────────┬────────────┘
         │            │           │              │
         │ HTTP+OIDC  │           │              │
         ▼            ▼           ▼              ▼
   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────────┐
   │MCP geo- │  │MCP      │  │MCP reno-│  │MCP dossi-│
   │coding   │  │market-  │  │vation   │  │er-pdf    │
   │Cloud Run│  │research │  │Cloud Run│  │Cloud Run │
   │FastMCP  │  │Cloud Run│  │FastMCP  │  │FastMCP   │
   └────┬────┘  └────┬────┘  └────┬────┘  └────┬─────┘
        │            │            │            │
        ▼            ▼            ▼            ▼
    Nominatim    Datos MITMA   Tarifas      reportlab
    (OSM)        oficiales     reforma      + GCS bucket
    geocodifica  por municipio España 2026  + signed URL


   ── EN PARALELO (asset arquitectónico para el jurado) ──

   Agent Engine · Reasoning Engine 8355329596958179328
   (Vertex AI · agente desplegado con `adk deploy agent_engine`,
    accesible vía playground console.cloud.google.com)
```

---

## 3. Stack Google Cloud — cada servicio

### 3.1 Vertex AI · Gemini 2.5 Flash
- **Qué hace:** modelo LLM que actúa como cerebro del agente. Recibe la
  instruction + el input del usuario, decide qué tool llamar en cada paso y
  redacta la respuesta final.
- **Cómo lo usamos:** vía Google ADK (`Agent(model="gemini-2.5-flash", ...)`).
  Cada llamada al modelo viaja a `europe-west1-aiplatform.googleapis.com`.
- **Por qué Flash y no Pro:** suficiente para function calling estructurado a
  tools deterministas. ~10× más barato y ~3× más rápido que Pro.

### 3.2 Vertex AI Agent Engine (Reasoning Engine)
- **Qué hace:** servicio gestionado para desplegar agentes ADK como recurso
  invocable, con su propia URL, playground (UI tipo chat de Google), tracing,
  versionado.
- **Cómo lo usamos:** `adk deploy agent_engine agent` empaqueta nuestro
  código, lo sube a un staging bucket y crea un Reasoning Engine que vive
  en Vertex AI.
- **Resource:** `projects/.../locations/europe-west1/reasoningEngines/8355329596958179328`.
- **Por qué está pero el frontend NO lo invoca:** el playground SÍ funciona,
  pero el endpoint REST `streamQuery` provoca que Gemini caiga a sintaxis
  "code interpreter" que Vertex rechaza con `UNEXPECTED_TOOL_CALL`. Mantener
  el Reasoning Engine desplegado vale como **asset arquitectónico** para la
  submission (probar "agent listo para Gemini Enterprise") y el playground
  es una demo independiente.

### 3.3 Cloud Run × 5 servicios
- **mcp-geocoding** — convierte direcciones españolas en lat/lon + barrio +
  distrito + provincia, usando Nominatim (OSM, gratuito).
- **mcp-market-research** — devuelve comparables sintéticos sobre una
  mediana de €/m² real de MITMA (municipio si lo tiene, provincia si no).
  Genera datos deterministas por coordenada para reproducibilidad.
- **mcp-renovation** — calcula presupuesto de reforma por capítulos
  (pintura, albañilería, fontanería, electricidad, mano de obra) con
  tarifas estándar España 2026, en 3 tiers (economy / standard / premium).
- **mcp-dossier-pdf** — genera el PDF de 4 páginas con reportlab, lo sube
  a GCS y devuelve una signed URL V4 válida 24h.
- **decomind-agent-ui** — el frontend FastAPI que sirve la UI y orquesta
  el agente. Habla con los 4 MCPs y los presenta al navegador como stream.
- **Por qué Cloud Run:** auto-scale a cero, pago por uso, HTTPS gestionado,
  IAM nativo. Encaja perfecto para microservicios MCP que reciben tráfico
  esporádico.

### 3.4 Cloud Build
- **Qué hace:** empaqueta el código local en imágenes Docker y las despliega
  a Cloud Run, todo sin Docker local instalado.
- **Cómo lo usamos:** `gcloud run deploy --source .` sube los fuentes a un
  bucket temporal, ejecuta el Dockerfile en Cloud Build, registra la
  imagen y crea/actualiza la revisión de Cloud Run.

### 3.5 Artifact Registry
- **Qué hace:** registro privado de imágenes Docker (sucesor de Container
  Registry).
- **Cómo lo usamos:** Cloud Build empuja las imágenes ahí automáticamente.
  Cloud Run las pull al desplegar revisiones.

### 3.6 IAM + Service Accounts + OIDC
- **decomind-agent-dev** (creada Día 1) — la SA de runtime del frontend y
  de los MCPs cuando se llaman entre sí. Tiene Editor en el proyecto +
  `serviceAccountTokenCreator` sobre sí misma (para self-sign de URLs).
- **service-PROJECT_NUMBER@gcp-sa-aiplatform-re** — service agent que
  Google crea automáticamente para Agent Engine. Necesita `run.invoker`
  sobre los 4 MCPs (lo concedimos manualmente).
- **OIDC ID tokens** — cada vez que el agente o el frontend llaman a un
  MCP, obtienen un ID token del metadata server (en Cloud Run) o por
  impersonación gcloud (en local dev) con la URL del MCP como audience.
  El MCP valida el token con IAM antes de servir.
- **Cero claves privadas descargables** — política org `iam.disableServiceAccountKeyCreation`
  activa. Toda auth federada vía metadata + impersonation.

### 3.7 Cloud Storage
- **Bucket `decomind-agent-dossiers`** — donde se guardan los PDFs
  generados. Acceso privado (no `allUsers`); se entregan vía signed URL
  V4 con expiración 24h.
- **Bucket `decomind-agent-staging`** — staging de artefactos de deploy
  (lo gestiona `adk deploy`).
- **Buckets internos de Cloud Build** — donde se sube el código fuente
  comprimido para el build remoto. Auto-gestionados.

### 3.8 IAM signBlob API
- **Qué hace:** firma cryptográfica como un service account sin necesitar
  su clave privada local.
- **Cómo lo usamos:** desde dentro del contenedor de `mcp-dossier-pdf`,
  el SDK de google-cloud-storage llama al endpoint `iam.serviceAccounts.signBlob`
  con la identidad de la SA del runtime para generar la signed URL V4.

### 3.9 Cloud Trace
- **Qué hace:** observabilidad distribuida — captura spans de cada
  llamada (modelo, tool, request HTTP) con timings.
- **Cómo lo usamos:** activado en el deploy de Agent Engine con
  `--trace_to_cloud`. Console: `console.cloud.google.com/traces/list`.

### 3.10 Vertex AI ADK (Agent Development Kit)
- **Qué hace:** framework Python para construir y orquestar agentes con
  LLMs + tools. Hace function calling, gestión de sesiones, integración
  con MCP, Runner, deploy a Agent Engine, todo.
- **Cómo lo usamos:** `Agent(model=..., tools=[McpToolset(...)], instruction=...)`
  + `InMemoryRunner(agent=...).run_async(...)`.

---

## 4. El agente — composición y pipeline

### 4.1 Composición
- 1 `Agent` ADK con:
  - **Model:** gemini-2.5-flash vía Vertex AI.
  - **Instruction:** ~120 líneas que describen el rol ("agente inmobiliario
    español"), el pipeline en 7 pasos (FASE 1 zona + valoración, FASE 2
    reforma, FASE 3 PDF), las reglas de calidad (no inventar datos, citar
    fuente, traducir features al inglés) y el idioma del entregable (PDF
    en EN, chat en ES).
  - **Tools:** 4 `McpToolset` (uno por MCP server). Cada uno habla MCP
    sobre Streamable HTTP con header `Authorization: Bearer <OIDC token>`.

### 4.2 Tools expuestas a Gemini (6 MCP servers)
| Tool | Servidor MCP | Hace |
|---|---|---|
| `geocode_address` | mcp-geocoding | dirección → lat/lon + municipio + provincia + distrito + CP (OSM/Nominatim) |
| `catastro_lookup` | mcp-catastro | coords → datos OFICIALES del Catastro: año construcción, uso, referencia catastral |
| `notariado_price` | mcp-notariado | **precio REAL de transacción** ante notario por código postal (fallback muni/provincia) |
| `find_comparables` | mcp-market-research | mediana €/m² MITMA (valor tasado, segunda fuente para contraste) |
| `estimate_market_value` | mcp-market-research | valor con **modelo hedónico de 6 factores** sobre precio Notariado |
| `estimate_room_cost` | mcp-renovation | coste de UNA estancia con desglose por oficio |
| `estimate_renovation_plan` | mcp-renovation | presupuesto completo de la vivienda con totales |
| `compute_renovation_roi` | mcp-market-research | revalorización + payback + recomendación |
| `render_dossier_pdf` | mcp-dossier-pdf | PDF + doble fuente + hedónico + gráficos → GCS signed URL |

### 4.2bis Arquitectura de valoración en capas (lo que la hace "buena")
```
1. Precio base   → NOTARIADO por código postal (precio REAL de compraventa) ← primario
                   fallback: municipio → provincia
2. Segunda fuente → MITMA municipal (valor tasado) — contraste + convergencia
3. Datos físicos → CATASTRO (año, uso, referencia — oficiales, no input manual)
4. Ajuste fino   → modelo HEDÓNICO 6 factores (superficie no lineal, planta+ascensor,
                   eficiencia energética, estado, antigüedad, exterior/interior)
5. Comparables reales (Catastro vecinos) + precios transacción → roadmap M2
```
**Fuentes oficiales gratuitas, sin scraping:** Notariado (compraventas reales),
Catastro (datos físicos), MITMA (valor tasado). Triangulación con indicador de
convergencia entre transacción real y tasación.

### 4.3 Pipeline típico de 9 tool calls (~30-40 s)
```
1. geocode_address                  ┐
2. catastro_lookup (año oficial)    │
3. notariado_price (precio REAL)    │  FASE 1 — Zona + valor actual
4. find_comparables (MITMA contraste)│
5. estimate_market_value (hedónico) ┘

6. estimate_renovation_plan         ┐  FASE 2 — Propuesta de reforma
7. estimate_market_value (post)     │
8. compute_renovation_roi           ┘

9. render_dossier_pdf               ─  FASE 3 — Entregable
```

---

## 4ter. Production-readiness — evals y guardrails

Dos propiedades que el challenge evalúa explícitamente (checklist "production
isn't just it runs").

### Modelo hedónico de valoración (`market_research/hedonic.py`)
No aplica un multiplicador plano por estado, sino 6 factores calibrados que
ajustan el €/m² base de la zona (lo que hace un tasador real):

| Factor | Efecto |
|---|---|
| Superficie | no lineal (pisos pequeños +€/m², grandes −) |
| Estado | obra_nueva 1.15 · reformado 1.08 · buen_estado 1.00 · a_reformar 0.82 · ruina 0.60 |
| Antigüedad | curva por años (centenario hasta −16%) |
| Planta + ascensor | 4º sin ascensor −18%; alto con ascensor +5%; ático +12% |
| Eficiencia energética | A +6% … G −10% |
| Exterior/interior | interior −10% |

Demostrable: mismo piso, ±35% solo cambiando ascensor + eficiencia. Desglose
100% auditable (el dossier muestra cada factor).

### Triangulación de fuentes (guardrail de calidad)
Dos fuentes oficiales independientes en paralelo:
- **Notariado** = precio REAL de compraventa (primario)
- **MITMA** = valor tasado (contraste)

`check_source_agreement` calcula la convergencia. Si <60% → `requires_review:
true` (el agente avisa de que conviene revisión humana antes de fijar precio,
en vez de dar un número a ciegas). Ej.: Benicàssim costa → Notariado 2.706 €/m²
vs MITMA 1.462 €/m² → convergencia 54% → flag de revisión.

### Guardrails (`mcp_servers/_guardrails.py`)
- **Input validators:** CP español válido (5 dígitos, provincia 01-52),
  superficie 10-2000 m², año 1800-2027, condición de lista cerrada. Input
  imposible → rechazo limpio con mensaje, no cálculo erróneo.
- **Output validators:** €/m² resultante dentro de rango España (200-25.000) y
  valor total plausible; si no → `warnings` + `requires_review`.

### Eval suite (`evals/`)
Suite de regresión reproducible contra las **APIs oficiales reales** (no mocks):
- 5 casos (Madrid, Marbella, Valencia, Bilbao, Benicàssim), 55 checks, **100%**.
- Por caso: geocoding resuelve, Catastro año (best-effort con degradación
  elegante), Notariado precio al nivel+rango esperado + nº transacciones,
  valoración hedónica en rango, triangulación disponible, ROI coherente.
- `evals/baseline.json` para detectar regresiones entre cambios.
- Premia la **degradación elegante**: si el Catastro no resuelve una parcela,
  el pipeline sigue dando valoración válida (no rompe).

Ejecutar: `python -m evals.run` · guardar baseline: `python -m evals.run --json evals/baseline.json`

---

## 4quater. ¿Por qué MCP y no funciones acopladas (tipo Azure Functions)?

Pregunta clave de arquitectura. Decomind V1 (producción, Azure) usa **Azure
Functions**: funciones HTTP que el código llama explícitamente
(`requests.post(...)`). El que orquesta es **el código** (imperativo, el flujo
A→B→C está cableado). V2 (este challenge) usa **MCP**: el que orquesta es **el
agente** (declarativo, Gemini decide qué tool llamar al vuelo).

**MCP (Model Context Protocol)** es un estándar abierto (Anthropic, adoptado por
Google/OpenAI) para que un LLM **descubra y use** herramientas. La palabra clave
es *estándar*: cada MCP se autodescribe (nombre, parámetros, qué devuelve) y el
modelo lee ese schema para saber usarla — sin que nadie programe la llamada.

| | Azure Functions (V1) | MCP (V2) |
|---|---|---|
| Quién orquesta | El código (hardcoded) | El agente (decide al vuelo) |
| Conoce las tools | Llamada escrita a mano | Las descubre (auto-descripción) |
| Acoplamiento | Flujo cableado en el worker | Tools intercambiables sin tocar el agente |
| Estándar | Propietario Azure | Abierto y portable (Gemini, Claude, …) |
| Schema/validación | Manual | El MCP publica su JSON Schema |

**Por qué importa aquí (no es moda):**
1. El challenge lo pide literal: *"move from static code to declarative intent…
   use MCP to securely connect to external tools"*. Es requisito/plus explícito.
2. Desacoplamiento real: añadir `notariado` y `catastro` NO tocó el agente —
   solo se levantaron dos MCP y el agente los descubrió. Con Azure Functions
   habría que reescribir el orquestador.
3. Auto-descripción: `notariado_price` se anuncia a Gemini (params, output);
   una Azure Function no se auto-describe a un LLM.
4. Portabilidad: los 6 MCP servirían igual con Claude u otro agente.

**Honestidad:** MCP no es "mejor" universalmente. Para un pipeline FIJO y
conocido (siempre A→B→C), las Azure Functions de V1 son más simples y rápidas
(sin la decisión del LLM en medio). MCP brilla cuando quieres que un AGENTE
decida el flujo, añadir/quitar capacidades sin reescribir, y un estándar
abierto. No son rivales: son la **V1 imperativa** vs la **V2 agéntica** del
mismo Dossier — exactamente la narrativa de refactor del Track 3.

---

## 5. Flujo end-to-end de una petición

```
[t=0]    Browser POST /chat {message: "..."}
[t=0]    Frontend Cloud Run:
           - Crea sesión ADK in-memory
           - Lanza Runner.run_async(message)
[t=0-3]  Runner pide a Gemini el primer plan
           → Gemini decide: function_call geocode_address(...)
[t=3-4]  Frontend recibe event.function_call
           → SSE "tool_call" → browser anima card "geocode_address running"
[t=4]    Runner ejecuta el tool:
           - Obtiene OIDC token (metadata server, audience = mcp-geocoding URL)
           - POST mcp-geocoding/mcp con MCP initialize
           - POST tool/call(geocode_address, {...})
           - mcp-geocoding llama a Nominatim, devuelve barrio + coords
[t=5]    Runner recibe function_response
           → SSE "tool_response" → browser marca card "done ✓" con summary
[t=5-7]  Runner pide a Gemini el siguiente paso
           → function_call find_comparables(lat, lon, province, ...)
... [repite ciclo para 6 tools más] ...

[t=~25]  Runner llega a render_dossier_pdf:
           - POST mcp-dossier-pdf/mcp con todo el dato
           - mcp-dossier-pdf renderiza PDF con reportlab a memoria
           - Sube a GCS (decomind-agent-dossiers/dossier_<ts>.pdf)
           - Genera V4 signed URL vía IAM signBlob
           - Devuelve {url, size_bytes, bucket}
[t=26]   Frontend recibe function_response
           → SSE "tool_response" → browser anima card del PDF +
             muestra botón "Open PDF" con la signed URL
[t=27]   Runner pide a Gemini el resumen final
           → text response con tablas markdown
[t=28]   Frontend stream texto a la burbuja del agente
[t=28]   SSE "done"
[t=28]   Usuario abre la URL → ve el PDF
```

---

## 6. Modelo de autenticación

```
Browser ──(public HTTPS)──► Frontend Cloud Run [allow-unauthenticated]
                              │
                              │ (runtime SA = decomind-agent-dev)
                              ▼
                          metadata.google.internal
                              │
                              │ ID token con audience = <MCP URL>
                              ▼
                          MCP Cloud Run [no-allow-unauthenticated]
                              │
                              │ Valida token vía IAM
                              ▼
                          run.invoker check (decomind-agent-dev)
                              │
                              ▼
                          FastMCP processes request
```

**Cero claves descargables.** Todas las identidades federadas.

---

## 7. Repo — dónde vive qué

```
C:\ProyectosVS\decomind-agent\
├── agent/                          ← El agente ADK
│   ├── __init__.py                 reexporta root_agent
│   ├── agent.py                    reexporta root_agent (entry para ADK deploy)
│   ├── main.py                     definición del Agent + toolsets HTTP/stdio
│   └── .env                        URLs MCP + project (gitignored, en local y bundlado al deploy)
│
├── mcp_servers/                    ← Los 4 servidores MCP
│   ├── _runtime.py                 helper para stdio (dev) vs HTTP (Cloud Run)
│   ├── geocoding/server.py         Nominatim wrapper
│   ├── market_research/
│   │   ├── data.py                 base €/m² + multiplicadores
│   │   ├── data_mitma.py           generado por scripts/parse_mitma
│   │   └── server.py               find_comparables + estimate_market_value + compute_roi
│   ├── renovation/
│   │   ├── rates.py                tarifas España 2026 por oficio
│   │   └── server.py               estimate_room_cost + estimate_renovation_plan
│   └── dossier_pdf/server.py       reportlab + GCS + signed URL
│
├── frontend/                       ← La Web UI
│   ├── app.py                      FastAPI + SSE + ADK Runner directo
│   ├── requirements.txt
│   ├── Dockerfile                  empaqueta frontend + agent + mcp_servers
│   └── static/
│       ├── index.html              UI dark con sidebar + chat
│       ├── style.css               
│       └── app.js                  SSE client + render de tool cards + PDF preview
│
├── scripts/                        ← Automatización
│   ├── deploy_mcps.ps1             deploy de los 4 MCPs a Cloud Run
│   ├── deploy_frontend.ps1         deploy de la UI a Cloud Run
│   ├── dump_mcp_urls.ps1           regenera .env.cloud con URLs Cloud Run
│   ├── grant_invoker.ps1           grant run.invoker a una SA en los 4 MCPs
│   ├── demo_set.py                 smoke test 6 direcciones (Madrid, BCN, Bilbao...)
│   ├── inspect_mitma.py            inspector del XLS del MITMA
│   ├── parse_mitma.py              parser que genera data_mitma.py
│   └── debug_lookup.py             diagnóstico de geocoding + lookup MITMA
│
├── data/raw/DatosVivienda.xls      ← XLS MITMA (gitignored, fuente de verdad de precios)
├── outputs/                        ← PDFs en local dev (gitignored)
│
├── docs/
│   ├── architecture.md             cómo encajan las piezas
│   ├── business-case.md            el caso de negocio (design partner, ROI)
│   ├── day-by-day.md               plan de 14 días
│   ├── isolation-rules.md          reglas de no-tocar-producción
│   └── system-overview.md          ← ESTE doc
│
├── requirements.txt                deps del agente para ADK deploy
├── pyproject.toml                  metadata + deps de dev
├── Dockerfile                      para los 4 MCPs
├── .dockerignore
├── .gitignore
└── README.md
```

---

## 8. Recursos clave — IDs y URLs

| Recurso | Valor |
|---|---|
| GCP Project | `decomind-agent-challenge` (project number 413729056213) |
| Region | `europe-west1` |
| Reasoning Engine (Agent Engine) | `8355329596958179328` |
| Playground del agente | https://console.cloud.google.com/vertex-ai/agents/agent-engines/locations/europe-west1/agent-engines/8355329596958179328/playground?project=413729056213 |
| MCP geocoding URL | `https://mcp-geocoding-ajrpcon4fq-ew.a.run.app` |
| MCP market-research URL | `https://mcp-market-research-ajrpcon4fq-ew.a.run.app` |
| MCP renovation URL | `https://mcp-renovation-ajrpcon4fq-ew.a.run.app` |
| MCP dossier-pdf URL | `https://mcp-dossier-pdf-ajrpcon4fq-ew.a.run.app` |
| Frontend UI URL | _pendiente del deploy_ |
| GCS bucket PDFs | `gs://decomind-agent-dossiers` |
| GCS bucket staging | `gs://decomind-agent-staging` |
| Runtime SA principal | `decomind-agent-dev@decomind-agent-challenge.iam.gserviceaccount.com` |
| Agent Engine service agent | `service-413729056213@gcp-sa-aiplatform-re.iam.gserviceaccount.com` |

---

## 9. Servicios Google encadenados (resumen para el jurado)

| # | Servicio | Función | Marca jurado |
|---|---|---|---|
| 1 | Vertex AI Gemini 2.5 Flash | LLM orquestador | ✅ |
| 2 | Vertex AI Agent Engine | Reasoning Engine desplegado | ✅ |
| 3 | Cloud Run × 5 | Microservicios FastAPI / FastMCP | ✅ |
| 4 | Cloud Build | CI/CD del deploy | ✅ |
| 5 | Artifact Registry | Container registry privado | ✅ |
| 6 | IAM + Service Accounts | Identidad federada | ✅ |
| 7 | OIDC ID tokens (metadata) | Auth service-to-service sin keys | ✅ |
| 8 | Cloud Storage | PDFs entregables | ✅ |
| 9 | IAM signBlob API | Signed URLs sin clave privada local | ✅ |
| 10 | Cloud Trace | Observabilidad distribuida (Agent Engine) | ✅ |
| 11 | ADK 2.1 | Framework de agentes | ✅ |
| 12 | MCP protocol 2025-11-25 | Estándar abierto de tools | ✅ |

**12 servicios federados con identidad gestionada, sin claves descargables.**

---

## 10. Estado y pendientes

**Operativo HOY (validado end-to-end):**
- ✅ Frontend Web UI (FastAPI + ADK directo + 4 MCPs HTTP) — funciona en local
  con los 7 tool calls + PDF. **Es el camino de producción real del producto.**
- ✅ Los 4 MCP servers en Cloud Run con auth IAM.
- ✅ Agent Engine desplegado + playground (con la salvedad del bug de
  code-interpreter del REST endpoint — el playground UI de Google sí funciona).

**Pendiente:**

| Pieza | Esfuerzo | Cuándo |
|---|---|---|
| Deploy del frontend UI a Cloud Run (ya funciona local) | 15 min | ahora mismo |
| Mejorar valoración: Catastro + modelo hedónico | 5-6 h | siguiente — núcleo de valor |
| Gráficos en el PDF (líneas/barras) | 3-4 h | opcional, polish |
| Vídeo demo 3-5 min | 4-6 h | crítico para submission |
| Landing page minimal | 3-4 h | opcional, refuerza "producto" |
| Comparativa antes/después (manual vs agente) | 2-3 h | activo para vídeo |
| README final + submission docs | 2 h | obligatorio |
| Cutover Día 14: submission | 1 h | 5 jun mediodía |

---

## 11. Costes estimados (los $500 GCP de sobra)

| Servicio | Coste por dossier completo | Notas |
|---|---|---|
| Vertex Gemini 2.5 Flash | ~$0.005 | ~10K tokens in/out |
| Cloud Run × 5 (request-time) | ~$0.0002 | ~30s × 5 invocations |
| Cloud Storage (escribir PDF) | ~$0.000005 | unos KB |
| Egress (PDF download) | ~$0.000010 | unos KB |
| Cloud Trace + Logging | ~$0.0001 | siempre |
| **Total por dossier** | **~$0.006** | **0,5 céntimos** |

Comparable: V1 producción Decomind ~$2.15 por dossier. **V2 reduce coste ~360×.**
Para 100K dossiers/año → V1 = $215K, V2 = $600. La narrativa de margen
del business case es real y verificable.

---

## 12. Línea editorial — qué decir y qué no

**Sí decir:**
- Refactor V2 del Dossier de producción (existe V1 hace meses en Azure).
- Stack 12 servicios Google federados, secure by default, cero keys.
- Datos públicos oficiales (MITMA — Ministerio de Transportes).
- 1 design partner validado: 4h → 10 min, ROI 12.9× en plan Pro.
- Coste por dossier baja de $2.15 a céntimos.

**No decir / no prometer:**
- Comparables individuales de Idealista (son sintéticos sobre mediana real).
- Cobertura municipal completa MITMA (~500 municipios, no los 8000+).
- Agente desplegado en Agent Engine como UI principal (el playground tiene
  un bug del modelo que rompe function calling; usamos ADK directo en el
  frontend pero Agent Engine sigue desplegado como asset).
- Renders fotorrealistas o shopping list IA (queda para M2).

---

## 13. Anexo — Ejemplo paso a paso (Calle Mayor 5, Madrid)

> Este es exactamente el recorrido que la **web muestra en vivo**: al enviar una
> dirección, cada paso aparece como una tarjeta con su resultado. Aquí escrito
> para estudiarlo sin ejecutar.

**Input del usuario:**
> "Valora Calle Mayor 5, Madrid, CP 28013. 95 m², a reformar, año desconocido.
>  Estancias: salón 24, cocina 11, baño 5, dormitorio 16, dormitorio 12,
>  pasillo 7. Tier standard. Genera el PDF."

**Paso 1 — `geocode_address`** (MCP geocoding → Nominatim/OSM)
- Entra: dirección "Calle Mayor 5", "Madrid", CP "28013"
- Sale: `lat 40.4163, lon -3.7055, municipio "Madrid", provincia "Madrid",
  distrito "Centro", barrio "Barrio de los Austrias"`
- Para qué: convierte texto en coordenadas + zona administrativa.

**Paso 2 — `catastro_lookup`** (MCP catastro → servicios web libres OVC)
- Entra: lat 40.4163, lon -3.7055
- Hace: coordenadas → parcela catastral más cercana → datos del inmueble
- Sale: `año 1914 (oficial), uso, referencia catastral 0244802VK4704C`
- Para qué: dato físico OFICIAL — el año ya no lo pone el usuario.

**Paso 3 — `notariado_price`** (MCP notariado → ArcGIS del Notariado)
- Entra: CP "28013", municipio "Madrid"
- Sale: `5.919 €/m² (precio REAL de transacción), 286 ventas notariales, nivel
  código_postal`
- Para qué: el precio base, de compraventas reales. Fuente PRIMARIA.

**Paso 4 — `find_comparables`** (MCP market-research → MITMA)
- Entra: lat/lon, provincia, municipio, distrito
- Sale: `mediana MITMA 5.286 €/m² (valor tasado)`
- Para qué: SEGUNDA fuente oficial, para contrastar con el Notariado.

**Paso 4b — `check_source_agreement`** (guardrail)
- Entra: 5.919 (Notariado) y 5.286 (MITMA)
- Sale: `convergencia 89%, agreement high, requires_review false`
- Para qué: triangula. Si divergieran mucho, marcaría revisión humana.

**Paso 5 — `estimate_market_value`** (modelo hedónico)
- Entra: 95 m², base 5.919 €/m² (Notariado), condición a_reformar, año 1914
- Hace: aplica 6 factores (superficie, estado 0.82, antigüedad 0.84, …)
- Sale: `valor actual ≈ 410.000 € (combined_factor ~0.73)`
- Para qué: ajusta el precio de zona a ESTE inmueble concreto.

**Paso 6 — `estimate_renovation_plan`** (MCP renovation)
- Entra: las 6 estancias + tier standard
- Sale: presupuesto por estancia y oficio, `total integral ≈ 16.600 €`
- Para qué: cuánto cuesta la reforma, desglosado.

**Paso 7 — `estimate_market_value`** otra vez (condición buen_estado)
- Sale: `valor post-reforma ≈ 540.000 €`
- Para qué: cuánto valdría ya reformado.

**Paso 8 — `compute_renovation_roi`**
- Entra: inversión 16.600 €, valor actual 410.000 €, post 540.000 €
- Sale: `revalorización neta ≈ +113.000 €, payback 7.8×, MUY RECOMENDADO`
- Para qué: ¿merece la pena reformar? El veredicto económico.

**Paso 9 — `render_dossier_pdf`** (MCP dossier-pdf → reportlab + GCS)
- Entra: todos los datos anteriores
- Hace: genera PDF de 4 páginas (portada, valoración doble-fuente + gráficos,
  presupuesto, ROI + veredicto), lo sube a Cloud Storage, firma una URL 24h
- Sale: `https://storage.googleapis.com/decomind-agent-dossiers/dossier_xxx.pdf`
- Para qué: el entregable final para el propietario.

**Resultado:** dossier completo en ~30 segundos, por céntimos. Cada número es
trazable a su fuente oficial (Notariado, Catastro, MITMA) — nada inventado.

### ¿Cómo verlo en la web?
1. Abre https://decomind-agent-ui-ajrpcon4fq-ew.a.run.app
2. Pulsa un ejemplo (o escribe una dirección) → "Run agent".
3. Verás aparecer las 9 tarjetas en vivo (este mismo recorrido) y, al final,
   el botón "Open PDF". Es el ejemplo paso a paso, interactivo.

---

_Generado desde docs/system-overview.md — regenerar PDF con
`python -m scripts.md_to_pdf docs/system-overview.md`._

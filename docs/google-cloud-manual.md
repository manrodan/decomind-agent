# Manual sencillo — Google Cloud de Decomind Agent

> Guía para entender QUÉ servicios de Google Cloud usamos, QUÉ hace cada uno,
> CÓMO conectan entre sí, y DÓNDE verlos en la consola web (todo se creó por
> CLI, aquí lo "visitamos" en la web para que quede claro).
>
> **Proyecto:** `decomind-agent-challenge` · **Número:** 413729056213 · **Región:** `europe-west1`

---

## 0. La idea en una imagen

Piensa en el sistema como un **restaurante**:

| Pieza del restaurante | Servicio Google | Rol |
|---|---|---|
| El chef que decide el menú | **Gemini (Vertex AI)** | El cerebro que decide qué hacer |
| El chef tiene su puesto fijo en cocina | **Agent Engine** | Donde "vive" el chef de forma permanente |
| Los 6 ayudantes especializados | **Cloud Run** (6 MCPs) | Cada uno hace UNA tarea (geocodificar, precios…) |
| El camarero que habla con el cliente | **Cloud Run** (frontend) | La web donde el usuario escribe |
| La cocina donde se montan los platos (contenedores) | **Cloud Build** | Empaqueta el código en "cajas" ejecutables |
| El almacén de cajas montadas | **Artifact Registry** | Guarda esas "cajas" (imágenes Docker) |
| La despensa de resultados (PDFs) | **Cloud Storage** | Guarda los dossiers generados |
| Los carnés y llaves de cada empleado | **IAM + Service Accounts** | Quién puede hacer qué |
| Las cámaras de seguridad y el libro de registro | **Cloud Logging + Trace** | Qué pasó y cuándo |

---

## 1. Cómo conectan entre sí (el flujo)

```
   Usuario (navegador)
        │
        ▼
   ┌─────────────────────┐
   │ Cloud Run: frontend │  ← la web "decomind-agent-ui"
   │ (FastAPI)           │
   └─────────┬───────────┘
             │ ejecuta el agente ADK
             ▼
   ┌─────────────────────┐        ┌──────────────────────┐
   │ Gemini 2.5 Flash    │◄──────►│ Vertex AI            │
   │ (decide qué tool)   │        │ (donde corre Gemini) │
   └─────────┬───────────┘        └──────────────────────┘
             │ llama herramientas (con token IAM)
   ┌─────────┼───────────┬───────────┬───────────┬──────────┐
   ▼         ▼           ▼           ▼           ▼          ▼
 geocoding catastro  notariado  market-res  renovation  dossier-pdf   ← 6 Cloud Run (MCP)
   │         │           │           │           │          │
   ▼         ▼           ▼           ▼           ▼          ▼
 OpenStreet Catastro  Notariado  datos MITMA  tarifas    reportlab
   Map      (oficial) (oficial)  (oficial)    reforma    → PDF → Cloud Storage

   (En paralelo, el mismo agente está desplegado en Agent Engine como recurso
    invocable, con su playground en la consola.)
```

**La conexión clave (auth):** cuando el frontend o el agente llaman a un MCP,
no usan contraseñas. Piden un **token temporal** (OIDC) a Google que dice "soy
la cuenta `decomind-agent-dev`", y el MCP comprueba con **IAM** que esa cuenta
tiene permiso (`run.invoker`). Cero claves guardadas en ningún sitio.

---

## 2. Servicio por servicio

### 2.1 Vertex AI (con Gemini 2.5 Flash)

- **Qué es:** la plataforma de IA de Google. Dentro vive **Gemini**, el modelo
  de lenguaje que razona.
- **Qué hace aquí:** es el cerebro del agente. Lee la petición ("valora este
  piso"), decide en qué orden llamar a las 6 herramientas, y redacta la
  respuesta final.
- **Dónde verlo:**
  `https://console.cloud.google.com/vertex-ai?project=decomind-agent-challenge`
- **Qué verás:** el panel de Vertex AI. En "Model Garden" están los modelos
  Gemini disponibles. No hay nada "tuyo" que configurar aquí — se usa bajo
  demanda y se paga por uso.
- **Creado por:** no se "crea", se habilitó la API (`aiplatform.googleapis.com`).

---

### 2.2 Agent Engine (Reasoning Engine)

- **Qué es:** un servicio donde "despliegas" un agente completo y queda como un
  recurso permanente con su propia URL y un **playground** (chat de prueba).
- **Qué hace aquí:** tenemos el agente Decomind desplegado ahí. Es el "sello"
  de que el agente está listo para Gemini Enterprise. Tiene un chat de prueba
  en la consola.
- **Dónde verlo:**
  `https://console.cloud.google.com/vertex-ai/agents/agent-engines?project=decomind-agent-challenge`
- **Qué verás:** tu agente "Decomind Dossier Agent" listado, con su ID
  (`8355329596958179328`). Si entras, hay un **Playground** para chatear con él.
- **Creado por:** `adk deploy agent_engine ... agent`

> Nota: el frontend web NO usa este Agent Engine (usa el agente directamente
> por rendimiento). Agent Engine queda como demostración de "desplegable en la
> plataforma de Google".

---

### 2.3 Cloud Run (el caballo de batalla — 7 servicios)

- **Qué es:** ejecuta contenedores (cajas con tu código) y los expone como una
  URL HTTPS. Escala solo: si nadie lo usa, se apaga (0 coste); si llega
  tráfico, arranca. Pagas solo por segundos de uso.
- **Qué hace aquí:** aloja **7 servicios**:
  - 6 servidores **MCP** (las herramientas del agente)
  - 1 **frontend** (la web)
- **Dónde verlo:**
  `https://console.cloud.google.com/run?project=decomind-agent-challenge`
- **Qué verás:** una lista con 7 servicios:

  | Servicio | Qué hace |
  |---|---|
  | `mcp-geocoding` | dirección → coordenadas + barrio (OpenStreetMap) |
  | `mcp-catastro` | datos oficiales del inmueble (año, uso) del Catastro |
  | `mcp-notariado` | precio REAL de venta (transacciones notariales) |
  | `mcp-market-research` | valor tasado MITMA + modelo hedónico |
  | `mcp-renovation` | presupuesto de reforma por estancia |
  | `mcp-dossier-pdf` | genera el PDF final |
  | `decomind-agent-ui` | la web del usuario |

  Si clicas un servicio: ves su URL, las "revisiones" (cada deploy crea una),
  métricas de uso, logs, y la pestaña de **seguridad** (quién puede invocarlo).
- **Creado por:** `gcloud run deploy <nombre> --source .` (scripts
  `deploy_mcps.ps1` y `deploy_frontend.ps1`).

---

### 2.4 Cloud Build

- **Qué es:** el servicio que coge tu código, lee el `Dockerfile`, y construye
  la "caja" (imagen de contenedor) en la nube — sin que necesites Docker en tu
  PC.
- **Qué hace aquí:** cada vez que ejecutas `deploy_mcps.ps1`, Cloud Build
  empaqueta el código y lo prepara para Cloud Run.
- **Dónde verlo:**
  `https://console.cloud.google.com/cloud-build/builds?project=decomind-agent-challenge`
- **Qué verás:** el historial de builds (uno por cada deploy), con logs de
  cada uno (verde = OK, rojo = falló). Útil para depurar si un deploy falla.
- **Creado por:** automáticamente al usar `gcloud run deploy --source .`

---

### 2.5 Artifact Registry

- **Qué es:** el almacén privado donde se guardan las "cajas" (imágenes Docker)
  que construye Cloud Build.
- **Qué hace aquí:** guarda las imágenes de los 7 servicios. Cloud Run las coge
  de aquí para arrancar.
- **Dónde verlo:**
  `https://console.cloud.google.com/artifacts?project=decomind-agent-challenge`
- **Qué verás:** un repositorio (`cloud-run-source-deploy`) con las imágenes de
  cada servicio y sus versiones.
- **Creado por:** automáticamente en el primer `gcloud run deploy`.

---

### 2.6 Cloud Storage

- **Qué es:** almacenamiento de archivos en la nube (como un Drive para
  programas). Los archivos se organizan en "buckets" (cubos).
- **Qué hace aquí:** dos cubos:
  - `decomind-agent-dossiers` → los **PDF** que genera el agente
  - `decomind-agent-staging` → archivos temporales de despliegue de Agent Engine
- **Dónde verlo:**
  `https://console.cloud.google.com/storage/browser?project=decomind-agent-challenge`
- **Qué verás:** los cubos. Si entras en `decomind-agent-dossiers`, los PDFs
  generados (`dossier_<numero>.pdf`). Son privados; se comparten con una
  "signed URL" temporal de 24h.
- **Creado por:** `gcloud storage buckets create gs://...`

---

### 2.7 IAM + Service Accounts (identidades y permisos)

- **Qué es:**
  - **Service Account (SA):** una "cuenta de robot" — identidad que usan los
    programas (no personas) para actuar.
  - **IAM:** el sistema de permisos — define qué puede hacer cada cuenta.
- **Qué hace aquí:**
  - `decomind-agent-dev` es la SA con la que corren el frontend y el agente.
    Tiene permiso para llamar a los MCPs y escribir PDFs.
  - `service-...@gcp-sa-aiplatform-re...` es la SA del Agent Engine (la crea
    Google), también con permiso para llamar a los MCPs.
  - Los MCPs están "cerrados": solo cuentas con el rol `run.invoker` pueden
    llamarlos. Por eso concedimos ese permiso a las 2 SAs.
- **Dónde verlo:**
  - Cuentas robot:
    `https://console.cloud.google.com/iam-admin/serviceaccounts?project=decomind-agent-challenge`
  - Permisos del proyecto:
    `https://console.cloud.google.com/iam-admin/iam?project=decomind-agent-challenge`
- **Qué verás:** la lista de service accounts (verás `decomind-agent-dev`). En
  IAM, qué rol tiene cada cuenta. En cada servicio de Cloud Run (pestaña
  PERMISSIONS) verás qué cuentas pueden invocarlo.
- **Creado por:** `gcloud iam service-accounts create ...` y los scripts
  `grant_invoker.ps1`.

> **Por qué no hay contraseñas:** la organización bloquea descargar "claves" de
> service account (política de seguridad). En su lugar, todo usa **tokens
> temporales** que se piden al vuelo. Más seguro: no hay nada que robar.

---

### 2.8 Cloud Logging (registro)

- **Qué es:** el "libro de registro" — guarda todos los mensajes que emiten los
  servicios.
- **Qué hace aquí:** cada MCP, el frontend y el Agent Engine escriben logs.
  Los usamos para depurar (ej. los 403 que arreglamos).
- **Dónde verlo:**
  `https://console.cloud.google.com/logs/query?project=decomind-agent-challenge`
- **Qué verás:** un buscador de logs. Puedes filtrar por servicio (ej.
  `mcp-notariado`) y ver qué hizo en cada petición.
- **Creado por:** automático (todo servicio loguea).

---

### 2.9 Cloud Trace (rendimiento)

- **Qué es:** mide cuánto tarda cada paso de una petición (un "cronómetro
  distribuido").
- **Qué hace aquí:** el Agent Engine está desplegado con trazas activadas.
  Muestra el tiempo de cada tool call.
- **Dónde verlo:**
  `https://console.cloud.google.com/traces/list?project=decomind-agent-challenge`
- **Qué verás:** una lista de trazas; al abrir una, el desglose temporal de
  cada llamada (modelo, herramientas). Bueno para el vídeo: "X tool calls en
  N segundos".
- **Creado por:** `adk deploy ... --trace_to_cloud`

---

## 3. Paseo recomendado por la consola (5 min)

Haz este recorrido una vez para que todo "encaje" visualmente:

1. **Cloud Run** → ves los 7 servicios. Clica `mcp-notariado` → pestaña
   "Revisiones" (cada deploy) y "Registros" (sus logs).
   `https://console.cloud.google.com/run?project=decomind-agent-challenge`

2. **Service Accounts** → ves `decomind-agent-dev` (la identidad de todo).
   `https://console.cloud.google.com/iam-admin/serviceaccounts?project=decomind-agent-challenge`

3. **Cloud Storage** → entra en `decomind-agent-dossiers` → ves los PDFs.
   `https://console.cloud.google.com/storage/browser?project=decomind-agent-challenge`

4. **Agent Engine** → tu agente listado + playground.
   `https://console.cloud.google.com/vertex-ai/agents/agent-engines?project=decomind-agent-challenge`

5. **Cloud Build** → el historial de construcciones.
   `https://console.cloud.google.com/cloud-build/builds?project=decomind-agent-challenge`

6. **Trace** → trazas del agente.
   `https://console.cloud.google.com/traces/list?project=decomind-agent-challenge`

---

## 4. Glosario CLI ↔ consola (qué creó cada comando)

| Lo que ejecutaste (CLI) | Qué creó | Dónde verlo |
|---|---|---|
| `gcloud services enable aiplatform...` | Activó Vertex AI | Vertex AI |
| `gcloud iam service-accounts create decomind-agent-dev` | La cuenta robot | Service Accounts |
| `gcloud run deploy mcp-* --source .` | Los 6 MCP + build + imagen | Cloud Run / Cloud Build / Artifact Registry |
| `gcloud run deploy decomind-agent-ui` | La web | Cloud Run |
| `scripts/grant_invoker.ps1` | Permiso `run.invoker` a las SAs | Cloud Run → cada servicio → Permissions |
| `gcloud storage buckets create` | Los cubos de archivos | Cloud Storage |
| `adk deploy agent_engine` | El agente en Agent Engine | Vertex AI → Agent Engines |
| `gcloud auth application-default login` | Tu acceso local (ADC) | (no se ve; es tu credencial local) |

---

## 5. Coste (tranquilidad)

Casi todo escala a cero: si nadie usa el sistema, **no pagas** (Cloud Run
apagado). Un dossier completo cuesta **~0,5 céntimos**. Los $500 de crédito
del challenge dan para decenas de miles de dossiers. Lo único "siempre
encendido" con coste mínimo: almacenamiento de los PDFs (céntimos al mes).

---

_Para regenerar este manual en PDF: `python -m scripts.md_to_pdf docs/google-cloud-manual.md`_

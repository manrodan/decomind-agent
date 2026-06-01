# Resumen de arquitectura — Decomind Agent

> Dos niveles: para cualquiera (sin tecnicismos) y para técnicos (con
> equivalencias Azure, porque venimos de ahí).

---

## NIVEL 1 — Para explicar a cualquiera (sin idea técnica)

Imagina una **asesoría inmobiliaria con un experto y sus ayudantes**:

- Llega un cliente y dice: *"valórame este piso de Calle Mayor 5"*.
- Un **experto** (la IA, Gemini) escucha y **organiza el trabajo**. Él no calcula
  a mano; reparte tareas a **6 ayudantes especializados**:
  - uno localiza la dirección en el mapa,
  - otro consulta el **año y datos oficiales** del inmueble (Catastro),
  - otro mira **a cuánto se han vendido de verdad** pisos en esa calle (Notariado),
  - otro consulta el **valor tasado oficial** (Ministerio),
  - otro calcula el **presupuesto de reforma**,
  - otro **monta el informe en PDF** bonito.
- El experto junta todo, **compara las fuentes** (¿el precio real y la tasación
  coinciden?), da un **veredicto** y entrega un **PDF profesional** en ~30 seg.

**Lo clave para alguien no técnico:**
- Los números **no se los inventa la IA**: vienen de **fuentes oficiales del
  Estado** (Notariado, Catastro, Ministerio). La IA solo organiza y redacta.
- Lo que un agente inmobiliario hacía en **4 horas**, esto lo hace en **minutos**.
- Todo vive "en la nube" de Google: se enciende solo cuando alguien lo usa y se
  apaga después (por eso cuesta céntimos).

---

## NIVEL 1.5 — Cómo está construido de verdad (sencillo)

El sistema son **3 capas** + las fuentes de datos:

```
   ┌───────────────────────────────────────────────┐
   │  CAPA 1 — La web                               │
   │  Una página donde el usuario escribe la        │
   │  dirección. (1 servicio en la nube)            │
   └───────────────────────┬───────────────────────┘
                           │
   ┌───────────────────────▼───────────────────────┐
   │  CAPA 2 — El cerebro (el agente)               │
   │  La IA (Gemini) que organiza el trabajo y      │
   │  decide a qué ayudante llamar y cuándo.        │
   └───────────────────────┬───────────────────────┘
                           │ reparte tareas
   ┌───────────────────────▼───────────────────────┐
   │  CAPA 3 — Las 6 herramientas                   │
   │  6 mini-programas independientes, cada uno      │
   │  hace UNA cosa (mapa, catastro, precios,        │
   │  tasación, reforma, PDF). (6 servicios)         │
   └───────────────────────┬───────────────────────┘
                           │ consultan
   ┌───────────────────────▼───────────────────────┐
   │  FUENTES OFICIALES (gratuitas, del Estado)      │
   │  Notariado · Catastro · Ministerio · Mapas      │
   └───────────────────────────────────────────────┘
```

**Qué se desplegó realmente:** 7 "mini-programas" en cajas independientes (la
web + las 6 herramientas), cada uno en **Cloud Run** (se encienden solos al
usarse). Además, el cerebro también está publicado aparte en **Agent Engine**
(la plataforma de agentes de Google) con un chat de prueba.

**Recorrido de una petición, en simple:**
1. Escribes "Calle Mayor 5, Madrid, 95 m²" en la web.
2. El cerebro (Gemini) lo lee y va llamando a las herramientas **en orden**:
   localiza → mira el catastro (año) → mira precios reales de venta → mira la
   tasación → calcula la reforma → calcula si compensa → monta el PDF.
3. Mientras lo hace, **ves cada paso aparecer en pantalla** (no es una caja
   negra).
4. En ~30 segundos tienes el PDF profesional con la valoración.

**Las dos ideas que lo hacen sólido:**
- **La IA no inventa números.** Organiza y redacta, pero los precios vienen de
  fuentes oficiales y los cálculos los hace código exacto.
- **Cada herramienta es independiente.** Añadir una nueva (p. ej. "precios de
  alquiler") no obliga a tocar el resto — se enchufa y el cerebro la descubre.

---

## NIVEL 2 — Para técnicos (con equivalencias Azure)

### Mapa de servicios: GCP ↔ Azure

| Función | Google Cloud (lo que usamos) | Equivalente Azure (lo que ya conoces) |
|---|---|---|
| Ejecutar contenedores con escala a 0 | **Cloud Run** | Azure **Container Apps** (o App Service) |
| Funciones sueltas | Cloud Functions | Azure **Functions** |
| Orquestar Kubernetes | GKE | **AKS** |
| Construir imágenes en la nube | **Cloud Build** | Azure **DevOps Pipelines** / GitHub Actions |
| Registro de imágenes Docker | **Artifact Registry** | Azure **Container Registry (ACR)** |
| Almacenamiento de archivos | **Cloud Storage** (buckets) | Azure **Blob Storage** (containers) |
| Identidades de programas | **Service Account** | **Managed Identity** / Service Principal |
| Permisos (quién puede qué) | **IAM** (roles) | Azure **RBAC** (roles) |
| Políticas de organización | **Organization Policies** | Azure **Policy** |
| Plataforma de IA / LLMs | **Vertex AI** (Gemini) | **Azure AI Foundry** / Azure OpenAI |
| Agente desplegado gestionado | **Agent Engine** (Reasoning Engine) | (Azure AI Agent Service, equivalente reciente) |
| Logs centralizados | **Cloud Logging** | Azure **Monitor / Log Analytics** |
| Trazas de rendimiento | **Cloud Trace** | Azure **Application Insights** |
| Secretos | (no usamos; federación) | Azure **Key Vault** |
| Tokens de identidad federada | **OIDC + metadata server** | **Managed Identity tokens (IMDS)** |

### Diagrama

```
Usuario (navegador)
   │
   ▼
Cloud Run: frontend (FastAPI)        ← como un Azure Container App
   │  ejecuta el agente ADK in-process
   ▼
Gemini 3.5 Flash (Vertex AI)         ← como Azure OpenAI
   │  decide qué herramienta llamar
   ▼
6× Cloud Run (servidores MCP)        ← 6 Container Apps, cada uno una tool
   │   geocoding · catastro · notariado · market-research · renovation · dossier-pdf
   ▼
Fuentes oficiales (Nominatim, Catastro, Notariado, MITMA) + Cloud Storage (PDFs)

(En paralelo: el mismo agente desplegado en Agent Engine, con playground.)
```

### Cómo se hablan entre sí (auth)
Sin contraseñas. El frontend corre como una **Service Account**
(`decomind-agent-dev`). Para llamar a un MCP, pide un **token OIDC temporal**
(1h) al metadata server y lo manda en la cabecera; el MCP valida con **IAM** que
esa cuenta tiene permiso (`run.invoker`). **Idéntico concepto a una Managed
Identity de Azure llamando a otro servicio con un token de IMDS** — cero claves
guardadas.

### El principio de diseño más importante
**El LLM orquesta; el código calcula.** Gemini decide el flujo y redacta, pero
los números (valoración, presupuesto, ROI) los produce **código determinista**.
Por eso es reproducible y auditable, no una alucinación.

---

## ¿Qué es una Service Account? (en detalle, desde Azure)

**En una frase:** es una **cuenta de "robot"** — una identidad que usan los
**programas** (no las personas) para autenticarse y tener permisos.

**Tu equivalente en Azure:** una **Managed Identity** (o un Service Principal).
Cuando en Azure una Function accede a un Blob sin poner credenciales, usa su
Managed Identity. En GCP es exactamente lo mismo con una Service Account.

**En nuestro proyecto:**
- `decomind-agent-dev@decomind-agent-challenge.iam.gserviceaccount.com` es la
  Service Account con la que **corren** el frontend y los 6 MCP.
- Tiene permisos (roles IAM): puede invocar los MCP (`run.invoker`), escribir
  PDFs en el bucket (`storage.objectAdmin`), usar Vertex AI.
- **No tiene contraseña descargable** (la organización lo prohíbe). En su lugar,
  obtiene **tokens temporales** del entorno (metadata server) — como los tokens
  de Managed Identity en Azure (IMDS).

**Diferencias con una cuenta de persona:**
| | Cuenta de persona | Service Account |
|---|---|---|
| Quién la usa | Un humano (tú, info@decomind.es) | Un programa/servicio |
| Login | Con tu contraseña + 2FA | Con tokens automáticos del entorno |
| Para qué | Administrar, ver consola | Que el código actúe con permisos |

**Por qué importa:** así el agente actúa con **permisos mínimos y acotados**
(solo lo que necesita), sin que ningún humano comparta su contraseña, y sin
claves guardadas que se puedan filtrar. Es el modelo "secure by default".

---

_Regenerar PDF: `python -m scripts.md_to_pdf docs/arquitectura-resumen.md`_

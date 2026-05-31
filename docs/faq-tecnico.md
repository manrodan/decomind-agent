# FAQ técnico — Decomind Agent

> Preguntas que el jurado (o un inversor) puede disparar, con respuestas
> defendibles. Pensado para repasar antes del vídeo y para una defensa en vivo.
> Cada respuesta incluye el "por qué" y la honestidad sobre límites.

---

## A. Arquitectura y tecnología

### A1. ¿Por qué MCP y no funciones acopladas (tipo Azure Functions)?
Azure Functions (V1 producción) = **el código orquesta** (flujo A→B→C cableado).
MCP (V2) = **el agente orquesta** (Gemini descubre las tools y decide al vuelo).
MCP es un estándar abierto: cada herramienta se autodescribe (nombre, params,
output) y el modelo lee ese schema. Prueba del desacoplamiento: añadir Notariado
y Catastro **no tocó el agente** — se levantaron los MCP y el agente los
descubrió. El challenge lo pide literal ("declarative intent… use MCP").
*Honestidad:* para un pipeline fijo, las Functions son más simples; MCP brilla
cuando un agente decide el flujo y quieres añadir capacidades sin reescribir.

### A2. ¿Por qué Cloud Run y no Cloud Functions ni GKE?
Cloud Run corre **contenedores** (un MCP es un proceso FastMCP/uvicorn) con
**escala a cero** (si nadie lo usa, 0€) y sin gestionar infraestructura. Cloud
Functions es más rígido para servidores con sesión MCP; GKE (Kubernetes) sería
sobredimensionado (nodos encendidos 24/7) para 6 microservicios de tráfico
esporádico. Por eso el coste sale en céntimos. *Honestidad:* con miles de
req/seg constantes o GPUs, GKE empezaría a tener sentido.

### A3. ¿Cómo se autentica el agente con los MCP sin contraseñas?
Federación de identidad: el agente pide al **metadata server** de Cloud Run un
**ID token OIDC** (firmado por Google, caduca en 1h) que dice "soy
decomind-agent-dev". Llama al MCP con ese token; el MCP valida con **IAM** que
esa cuenta tiene `run.invoker`. **Nunca hay una clave guardada** — la org
bloquea descargar claves de service account. Si alguien entra al contenedor, no
hay nada que robar; los tokens son efímeros y por destino. Es el
"least-privilege + secret management" del checklist.

### A4. ¿Qué hace el modelo hedónico vs lo que hace Gemini?
**Gemini orquesta, el código calcula.** Gemini decide qué tools llamar y con qué
datos, y redacta el veredicto — pero **NO calcula el precio**. El cálculo lo
hace una fórmula determinista (6 factores × €/m² base). Así el número es
reproducible y auditable (cada factor visible en el PDF), y Gemini aporta lo que
sabe (lenguaje, orquestación), no lo que hace mal (aritmética precisa). Esto
distingue un AVM serio de "preguntarle a un chatbot cuánto vale un piso".

### A5. ¿Por qué Agent Engine si la web usa el agente directamente?
Es el **mismo agente, dos puertas**. La web (`decomind-agent-ui`) lo ejecuta
in-process (ADK directo) para UX. Agent Engine lo tiene desplegado como recurso
gestionado en Vertex AI con su playground — el "sello Gemini Enterprise" que el
Track 3 valora. Con gemini-3.5-flash ambos funcionan igual. La web demuestra
**producto**; Agent Engine demuestra **plataforma/distribución empresarial**.

### A6. ¿Por qué Gemini 3.5 Flash y no Pro?
El modelo solo **orquesta** (las tools calculan), así que no necesita el modelo
más potente. Flash es ~10× más barato y rápido, con function calling sólido.
3.5 Flash ("parallel agentic execution") además resolvió un fallo de function
calling que tenía 2.5 en el playground de Agent Engine. `temperature=0` para
reproducibilidad.

---

## B. Datos y calidad

### B1. ¿Por qué tres fuentes oficiales (Notariado + MITMA + Catastro)?
Cada una mide algo distinto: **Notariado** = precio real de compraventa (por
CP); **MITMA** = valor tasado (hipoteca, conservador); **Catastro** = datos
físicos (año, m², uso — no es precio). Notariado y MITMA son dos precios
independientes → si concuerdan (convergencia alta), valoración robusta; si
divergen, el guardrail marca revisión. Dos números oficiales que coinciden es
**defendible** ante un propietario; uno solo es una opinión.

### B2. ¿Esto es legal? ¿Hacéis scraping?
**Cero scraping.** Solo fuentes **oficiales y públicas**: Notariado (Portal
Estadístico, API ArcGIS pública), Catastro (servicios web libres OVC), MITMA
(estadística pública descargable). Descartamos Idealista scraping (ToS, riesgo)
y el Valor de Referencia del Catastro (requiere certificado). Es un
diferenciador: datos oficiales, no datos "raspados" de dudosa legalidad.

### B3. ¿Qué pasa si una fuente o API falla?
**Degradación elegante** (best-effort). Si el Catastro no resuelve una parcela,
el pipeline sigue con valoración válida (sin el año oficial, factor neutro). Si
el Notariado no tiene dato de un CP, hace fallback a municipio → provincia. La
eval suite **premia** esta robustez: un caso (Bilbao) pasa precisamente porque
degrada limpio sin romper.

### B4. ¿Cómo garantizáis que el agente no inventa números?
Tres capas: (1) **tools deterministas** — el cálculo es código, no LLM;
(2) **guardrails** — validan inputs (CP, m², año) y marcan outputs fuera de
rango de mercado; (3) **temperature=0** — reproducibilidad. Además, cada número
es **trazable** a su fuente oficial en el PDF. El LLM no fija precios.

### B5. ¿Cómo sabéis que funciona? ¿Cómo medís la calidad?
**Eval suite** (`evals/`): 5 casos reales, 55 checks, **100%**, ejecutada contra
las APIs oficiales reales (no mocks). Verifica geocoding, año Catastro, nivel y
rango del precio Notariado, valoración hedónica, triangulación y ROI. Hay
`baseline.json` para detectar regresiones entre cambios. Es una suite de
regresión reproducible, no "probamos a mano".

### B6. ¿En qué se diferencia de pedirle a ChatGPT que valore un piso?
Un chatbot **alucina** un número plausible sin fuente. Decomind Agent: (a) usa
**precios reales de transacción** del Notariado por código postal; (b) **calcula**
con un modelo hedónico determinista (no estima a ojo); (c) **triangula** dos
fuentes oficiales; (d) es **trazable** (cada dato citado) y **reproducible**
(mismo piso → mismo valor). Es la diferencia entre una valoración defendible y
una conjetura.

### B7. ¿Maneja datos personales (RGPD)?
El dossier trabaja con datos del **inmueble** (dirección, m², año, precio de
zona), no con datos personales del propietario. Las fuentes son agregadas y
anonimizadas (el Notariado publica estadística anonimizada). El nombre del
fichero PDF lleva timestamp no adivinable. Para producción con datos de cliente,
roadmap: signed URLs/tokens en vez de URL pública.

---

## C. Negocio y producto

### C1. ¿Por qué el vertical inmobiliario español?
Es donde Decomind ya opera, con un **design partner real** (inmobiliaria) que
valida el problema: un dossier de venta le llevaba **4 horas**; con Decomind,
**10 minutos**. Mercado claro (~50.000 agentes en España), problema doloroso
(captación), y datos oficiales españoles disponibles gratis (Notariado,
Catastro, MITMA). Expansión natural a LatAm (mismo idioma, mismo problema).

### C2. ¿Cuál es el modelo de negocio?
Decomind ya factura en producción (Stripe) con 3 planes (Esencial 59€ / Pro 89€
/ Agencia 199€). El agente es la **V2 del Dossier**, núcleo del plan Agencia.
Unit economics: V1 ~2,15€/dossier → V2 ~0,03€/dossier (mejora de margen). Vía
roadmap: listado en Google Cloud Marketplace.

### C3. ¿Cómo encaja con la producción actual (Decomind en Azure)?
Producción (app, datos, Stripe) está en **Azure**; el agente es un **refactor
aislado en GCP** que no toca producción. Coexisten: el Dossier V1 (Azure) sigue
sirviendo; V2 (GCP, este agente) es la evolución agéntica. Roadmap: integrar V2
como opción premium del plan Agencia. La narrativa Track 3 es exactamente esa:
refactor de un agente funcional a arquitectura GCP escalable.

### C4. ¿Qué es lo más innovador?
(1) Triangulación de **precio real de transacción** (Notariado) con tasación
(MITMA), con indicador de convergencia — pocos AVM combinan ambas. (2) **Datos
oficiales gratuitos** vía MCP, sin scraping. (3) Separación limpia
**orquestación (LLM) vs cálculo (determinista)** → valoración reproducible y
auditable. (4) Arquitectura agéntica con tools intercambiables (se añaden
fuentes sin tocar el agente).

### C5. ¿Cómo escala?
Cloud Run escala a cero y hacia arriba automáticamente; coste por dossier en
céntimos; tools desacopladas (añadir capacidades sin reescribir). El cuello de
botella futuro no es técnico sino de **datos premium** (comparables
individuales reales = Idealista Data / Registradores, roadmap M2, financiable
con tracción o el premio).

---

## Límites honestos (lo que NO afirmamos)
- Comparables **individuales** reales: hoy agregados oficiales por zona; los
  individuales (Idealista Data) son roadmap M2.
- Cobertura: ~500 municipios MITMA / CP con datos Notariado; zonas muy pequeñas
  degradan a provincia.
- Sin renders fotorrealistas ni shopping list (estaban en V1; M2 como add-on).
- Valor de Referencia del Catastro: descartado (requiere certificado).

---

_Regenerar PDF: `python -m scripts.md_to_pdf docs/faq-tecnico.md`_

# Business Case — Decomind Agent

> **Esqueleto.** Rellenar con datos reales del design partner y métricas de los modelos. Cada `[TBD]` marca un dato pendiente.
>
> **Contexto honesto a fecha 2026-05-22:**
> - Producto en producción muy reciente (mayo 2026).
> - **1 cliente activo (inmobiliaria boutique)** — design partner.
> - Sin MRR significativo. Stripe live y funcionando.
> - **Pivote narrativo:** no vendemos tracción, vendemos *problem-validated + design-partner-validated + technical inflection point*.

---

## 1. El problema

Un agente inmobiliario en España invierte **~[TBD] horas** preparando el dossier de venta de un piso: valoración de mercado, comparables, propuesta de reforma, mensaje al propietario, anuncio para portales. El proceso actual combina Idealista/Fotocasa, Google Maps, llamadas a contactos, plantillas Word y Excel. Es **manual, lento y no escala** con la cartera de captaciones.

> *Dato a obtener del design partner: "¿cuántas horas te lleva un dossier completo sin Decomind?"*

## 2. La solución

**Decomind Agent** es la **V2 del Dossier de venta** que Decomind ya tiene en producción.

**V1 (en producción hoy, Azure Functions):**
- Flujo "async-volcano": frontend encola job → worker procesa 5-10 min → callback HMAC.
- Orquestación imperativa hardcoded: 3 llamadas LLM en secuencia (Gemini Pro shopping list + Gemini Flash Image renders + GPT-4o-mini timeline).
- Valoración: precio €/m² **introducido manualmente** por el agente inmobiliario (`ManualRoiProvider` devuelve `None` automático).
- Coste por dossier: varios € (modelos pesados + renders).
- Acoplado a Azure Storage Queues + Flask callback + custom HMAC.

**V2 (este challenge, GCP):**
- Orquestación declarativa con **Google ADK** + **Gemini 2.5 Flash** como cerebro.
- Tools desacopladas como **MCP servers** (geocoding · market-research · renovation · pdf-dossier), intercambiables sin tocar el agente.
- Valoración **automática** con datos oficiales del **MITMA** (Ministerio de Transportes, ~500 municipios).
- Latencia objetivo: **5-10 segundos** (vs 5-10 min en V1).
- Coste objetivo: **céntimos** (vs varios € en V1) gracias a Gemini Flash + tools determinísticas.
- Registrable en **Gemini Enterprise Agent Platform** y empaquetable para **Google Cloud Marketplace**.

> **No es un producto nuevo — es la misma utilidad para el propietario, una arquitectura preparada para escalar y un coste variable que mejora el margen del plan Pro.**

### Coexistencia con Deep Research

Decomind tiene además un **Deep Research** en producción (`deep-research-preview-04-2026`, $3-5/informe) para reportes largos de mercado por zona. **Coexiste** con el Agent V2:

| Producto | Granularidad | Uso |
|---|---|---|
| Deep Research | Zona / CP | Estratégico (¿me interesa esta zona?) |
| Agent V2 (este challenge) | Inmueble concreto | Operativo (¿qué digo del piso?) |

## 3. Design Partner Validation

| Campo | Valor |
|---|---|
| Cliente | [TBD — pedir permiso para citar nombre, si no "inmobiliaria boutique en {provincia}"] |
| Tipo | Inmobiliaria independiente |
| Tiempo medio dossier *antes* | **4 horas** |
| Tiempo medio dossier *con Decomind* | **10 minutos** |
| Reducción de tiempo | **−96%** (de 240 min a 10 min) |
| Dossiers generados desde lanzamiento | **20** |
| Captaciones mensuales | **10** (100% se procesan con Decomind) |
| Coste-hora del agente | **30 €/h** |
| Testimonial | *"Consigo demostrarle más rápido al propietario cómo vamos a comercializar su propiedad."* |
| ¿Aparece en vídeo demo? | **✅ Sí** |
| Razón de retención | Rapidez y precisión |

**Frame:** "Validated with design partner, ready to scale beyond V1."

### Métricas derivadas — los números del vídeo

Datos reales (no proyecciones):

- **Tiempo ahorrado por dossier:** 3h 50min (3,83 h).
- **Tiempo ahorrado al mes** (10 captaciones): **38,3 h/mes ≈ 1 semana laboral completa.**
- **Tiempo ahorrado al año:** ~460 h/año ≈ **57 días laborables ≈ 2,5 meses laborales recuperados**.
- **Ahorro económico al mes** (38,3 h × 30 €/h): **1.150 €/mes**.
- **Ahorro económico al año:** **13.800 €/año**.
- **ROI plan Pro** (89 €/mes = 1.068 €/año): **12,9× retorno**.
- **ROI plan Agencia** (199 €/mes = 2.388 €/año): **5,8× retorno**.
- **Coste implícito por hora ahorrada** (plan Pro): **2,32 €/h** (vs. 30 €/h reales).
- **Adopción:** **100%** — el partner usa Decomind para todas sus captaciones, no es una herramienta más, es el flujo.

### Titulares para vídeo / submission

1. **"Un dossier inmobiliario pasa de 4 horas a 10 minutos."**
2. **"Una semana laboral recuperada al mes — por 89 €."**
3. **"ROI 12,9× confirmado con design partner real."**
4. **"100% de las captaciones del partner se procesan con Decomind."**

> Estos números son **honestos y verificables** — vienen de un cliente real, no de una proyección. Es exactamente el tipo de evidencia que un jurado de Google espera de un Track 3 (MVP listo para escalar).

## 4. Mercado (TAM / SAM)

- **~50.000 agentes inmobiliarios activos** en España (fuente: AEAPI / ANCI — confirmar dato).
- **Dato de design partner: 10 captaciones/mes = ~120/agente/año** (3-4x más alto que estimación inicial de 30/año).
- 50.000 agentes × 120 captaciones/año = **~6M dossiers/año** de TAM en España (vs. 1,5M estimado antes).
- Plan Pro 89€/mes × 50.000 agentes × 12 meses = **~53M €/año** TAM España.
- Plan Agencia 199€/mes (multi-usuario) para inmobiliarias medianas (~5.000 en España) = **~12M €/año** segmento empresarial.
- **Expansión natural:** LatAm hispanohablante (México, Colombia, Argentina, Chile) — mismo idioma, mismo problema, baja competencia local en español. TAM combinado x3.

## 5. Modelo de negocio (en producción)

| Plan | Mensual | Anual (~17% dcto.) | Quota dossiers/mes |
|---|---:|---:|---:|
| Esencial | 59€ | 49€ | 0 |
| Pro | 89€ | 74€ | 5 |
| Agencia | 199€ | 166€ | 15 |

- Stripe-first signup en producción desde mayo 2026.
- El agente refactorizado se posiciona como **núcleo del plan Agencia**.
- **Post-challenge:** listing en **Google Cloud Marketplace** para customers enterprise que prefieran billing GCP.

## 6. Unit economics — mejora del margen V1 → V2

### V1 (Dossier en producción hoy, Azure)

| Concepto | Coste estimado por dossier |
|---|---:|
| Gemini 2.5 Pro (shopping list por estancia) | ~0,80 € |
| Gemini 3.1 Flash Image (renders, ~5/dossier) | ~1,20 € |
| GPT-4o-mini (renovation timeline) | ~0,10 € |
| Function App Azure (10 min worker) | ~0,05 € |
| **Coste variable V1** | **~2,15 €** |

### V2 (este challenge, GCP)

| Concepto | Coste estimado por dossier |
|---|---:|
| Gemini 2.5 Flash (orquestador, ~10K tokens in/out) | ~0,02 € |
| MCP tools (Nominatim free + cálculos deterministas) | 0 € |
| Cloud Run (5-10 seg ejecución) | ~0,01 € |
| **Coste variable V2** | **~0,03 €** |

### Implicación

| Plan | Precio/mes | Dossiers/mes | Coste V1 | Coste V2 | Margen ganado/mes |
|---|---:|---:|---:|---:|---:|
| Pro | 89 € | 5 | 10,75 € | 0,15 € | **+10,60 €** |
| Agencia | 199 € | 15 | 32,25 € | 0,45 € | **+31,80 €** |

> Refactor V1 → V2 mejora el margen bruto del plan Pro en ~12% y del Agencia en ~16% del precio del plan. **Es exactamente el tipo de mejora que un jurado de Track 3 espera ver** ("from MVP to enterprise — better margins, better latency, better architecture").

### Renders y shopping list (decisión consciente)

V2 NO incluye renders fotorrealistas ni shopping list por estancia. Razón: son las funciones más caras de V1 (Flash Image + Gemini Pro) y aportan valor estético pero no decisión. **Roadmap M2:** MCP `decor-renders` + `shopping-list` opcionales para clientes que paguen extra. Las inmobiliarias que prefieren rapidez (la mayoría) usan V2 plano; las que necesitan pitch visual al propietario pagan add-on.

## 7. Por qué *ahora* (technical inflection)

- **ADK + MCP + Gemini Enterprise** hacen viable hoy una arquitectura agéntica que hace 12 meses requería integraciones custom frágiles y caras.
- El refactor del Track 3 sustituye orquestación secuencial Azure Functions por agente con tools nativos → estimación **−[TBD]% coste por dossier** y latencia menor.
- **Vertex AI evals** + **Agent Builder observability** permiten medir y mejorar el agente en producción de forma sistemática — algo que el MVP Azure no tiene.

## 8. Tracción honesta a fecha 2026-05

- Producto **live** en `decomind.es` y `app.decomind.es` desde mayo 2026.
- Sistema de pago Stripe **funcionando**, planes activos.
- **1 design partner** validando producto end-to-end.
- Pipeline comercial: [TBD nº leads / demos / contactos].
- Equipo: [TBD founders / FTE].
- Runway: [TBD si aplica].

> Anti-frame: no presumir de "miles de users" que no existen. El jurado de Google huele inflado a kilómetros. El frame correcto es **"newly-launched product with deep design-partner validation, refactoring to enterprise-grade GCP architecture to scale"**.

## 9. Uso de los premios y créditos

- **$500 créditos GCP** → inferencia Gemini + Vertex durante el challenge (cubre desarrollo + demo).
- **Si ganamos share del $90K:**
  - ~60% a aceleración comercial (sales contractor para cerrar 20 clientes en H2 2026).
  - ~30% a listing **live** en Google Cloud Marketplace + materiales enterprise.
  - ~10% a buffer infra para escalar.

## 10. Roadmap post-challenge

| Mes | Hito |
|---|---|
| M1 | Integración del agente refactorizado como núcleo del plan Agencia en producción Decomind |
| M2 | Listing **live** en Google Cloud Marketplace |
| M3 | 20 clientes pagando, primeros ingresos de Marketplace |
| M6 | Expansión LatAm — primer customer en México o Colombia |
| M12 | 200 clientes / [TBD] € ARR |

---

## Datos a pedir al design partner esta semana

1. ¿Cuántas horas tardas en preparar un dossier de venta completo *sin* Decomind?
2. ¿Cuántos dossiers has generado con Decomind desde que empezaste?
3. ¿Qué te hace seguir usándolo (o qué te haría dejarlo)?
4. ¿1 frase para citar como testimonial?
5. ¿Estarías dispuesto a aparecer 30s en un vídeo demo, o que cite tu inmobiliaria? (con anonimización si prefieres)
6. ¿Tu volumen mensual de captaciones?

## Datos a calcular esta semana (read-only desde producción)

> Recordatorio: lectura read-only, sin escrituras ni cambios. Ver `docs/isolation-rules.md`.

- Nº de dossiers generados en producción hasta hoy.
- Tiempo medio de pipeline (encolado → done) por dossier.
- Coste medio por dossier (suma de llamadas Gemini/OpenAI/Replicate).
- Distribución por feature (Dossier vs House Tour vs Deep Research vs Retoque).

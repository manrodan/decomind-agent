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

**Decomind Agent**: agente autónomo que toma una dirección + datos básicos del inmueble y entrega el dossier completo en minutos. Combina:

- Deep research de mercado local (scraping Idealista/Fotocasa + comparables geolocalizados).
- Valoración con costes laborales y de obra por provincia.
- Propuesta de reforma con renders fotorrealistas por estancia.
- PDF final listo para enviar al propietario.

Refactorizado en Track 3 a arquitectura agéntica nativa GCP (**ADK + MCP + Vertex AI + Gemini Enterprise**), reemplazando la orquestación secuencial en Azure Functions del MVP.

## 3. Design Partner Validation

| Campo | Valor |
|---|---|
| Cliente | [TBD — pedir permiso para citar nombre, si no "inmobiliaria boutique en {provincia}"] |
| Tipo | Inmobiliaria independiente |
| Tiempo medio dossier *antes* | **4 horas** |
| Tiempo medio dossier *con Decomind* | **[medir esta semana]** (asumir ~15-30 min) |
| Dossiers generados desde lanzamiento | **20** |
| Captaciones mensuales | **10** |
| Testimonial | *"Consigo demostrarle más rápido al propietario cómo vamos a comercializar su propiedad."* |
| ¿Aparece en vídeo demo? | **✅ Sí** |
| ¿Qué le hace seguir usándolo? | Rapidez y precisión |

**Frame:** "Validated with design partner, ready to scale beyond V1."

### Métricas derivadas (las que van al vídeo)

> Asumiendo conservador: Decomind reduce dossier de 4h → 30 min.

- **Tiempo ahorrado por dossier:** 3,5 h.
- **Tiempo ahorrado al mes** (10 captaciones): **35 h/mes ≈ 1 semana laboral completa devuelta al agente.**
- **Tiempo ahorrado anualizado:** ~420 h/año ≈ **52 días laborables**.
- **Ratio inversión / retorno:** plan Pro 89€/mes vs. 35h ahorradas → **coste implícito 2,5 €/h ahorrada** (vs. coste-hora real del agente inmobiliario ~25-40 €/h → ROI 10-16x).
- **Dossiers generados con Decomind / dossiers totales del partner:** 20 dossiers con Decomind en ~2 meses, 10 captaciones/mes → **100% adopción** (lo usa para todas sus captaciones).

> *Pedir al partner para cerrar el cálculo real:*
> - *Coste-hora propio (o el del agente que lo usa) → para el "ahorro €/mes" final.*
> - *Tiempo exacto que tarda hoy con Decomind (cronometrar 1 dossier).*

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

## 6. Unit economics (proyectados — primer mes de uso real)

| Métrica | Valor estimado |
|---|---:|
| Coste Gemini (orquestador + Deep Research) por dossier | [TBD] € |
| Coste Imagen 3 (renders, ~5/dossier) | [TBD] € |
| Coste tools externos (geocoding, scraping) | [TBD] € |
| **Coste total por dossier** | [TBD] € |
| Precio implícito en plan Pro (89€ / 5 dossiers) | 17,8 € |
| Precio implícito en plan Agencia (199€ / 15 dossiers) | 13,3 € |
| **Margen bruto plan Pro** | [TBD] % |
| **Margen bruto plan Agencia** | [TBD] % |

> *Honesto: datos preliminares, se afinan con primer mes completo. Sirve para mostrar viabilidad de unit economics al jurado.*

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

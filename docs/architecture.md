# Arquitectura del Agente

## Visión general

```
┌─────────────────────────────────────────────────────────────────────┐
│                          INPUT (del agente inmobiliario)            │
│  Dirección · CP · Superficie · Estado · Año · Presupuesto reforma   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
        ┌──────────────────────────────────────────────┐
        │  Decomind Agent  (Gemini 2.5 Flash, ADK)     │
        │  Orquesta tools en pipeline auditable        │
        └──────────────────────────────────────────────┘
            │           │             │            │
            │ stdio     │ stdio       │ stdio      │
            ▼           ▼             ▼            ▼
     ┌────────────┐ ┌─────────────┐ ┌──────────────┐ ┌─────────────┐
     │  MCP       │ │  MCP        │ │  MCP         │ │  MCP        │
     │ geocoding  │ │ market-     │ │ market-      │ │ market-     │
     │ (Nominatim)│ │ research    │ │ research     │ │ research    │
     │            │ │ find_comps  │ │ estimate_    │ │ compute_    │
     │            │ │             │ │ market_value │ │ reno_roi    │
     └─────┬──────┘ └──────┬──────┘ └──────┬───────┘ └──────┬──────┘
           │               │               │                │
           ▼               ▼               ▼                ▼
       barrio,        comparables    valor actual,      revalorización
       distrito,      + mediana      valor post-        neta + payback +
       lat/lon        €/m²           reforma            recomendación
           │               │               │                │
           └───────────────┴───────┬───────┴────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          OUTPUT (al agente inmobiliario)            │
│  • Resumen markdown: zona, valoración, ROI, veredicto              │
│  • Trazabilidad: cada dato citado con su tool de origen             │
│  • PDF dossier (Día 6 — MCP renovation+pdf)                         │
└─────────────────────────────────────────────────────────────────────┘
```

## Componentes

| Componente | Tecnología | Función |
|---|---|---|
| **Orquestador** | ADK (Google Agent Development Kit) + Gemini 2.5 Flash vía Vertex AI | Decide qué tools llamar y en qué orden. Razonamiento multi-step. |
| **MCP geocoding** | FastMCP + Nominatim (OpenStreetMap) | Dirección ES → lat/lon + barrio + distrito |
| **MCP market-research** | FastMCP + datos públicos agregados | Comparables + valoración + ROI |
| **MCP renovation** *(Día 5)* | FastMCP | Presupuesto de reforma por capítulos |
| **MCP dossier-pdf** *(Día 6)* | FastMCP + reportlab | Empaqueta resultado en PDF para enviar al propietario |

## Transporte y aislamiento

- Cada MCP server es un **proceso Python independiente**.
- Transport en desarrollo: **stdio** (el agente spawnea el server como subprocess).
- Transport en producción Marketplace: **HTTP/SSE** sobre Cloud Run (un servicio por MCP).
- **Aislamiento total** de producción Decomind: este repo no llama a Flask, Azure Functions, BBDD pricing ni Storage. Ver `isolation-rules.md`.

## Datos hoy vs. roadmap

| Capa | Hoy (MVP challenge) | Roadmap productivo |
|---|---|---|
| Geocoding | Nominatim (real, gratuito) | Mantener Nominatim + fallback Google Maps API |
| €/m² base por provincia | INE/Tinsa/Notarios agregados (real) | INE microdatos + Notarios CIEN (mensual por CP) |
| Comparables individuales | **Sintéticos** deterministas desde mediana | Idealista Data API (contrato B2B) — M2 |
| Valoración pro / oficial | Heurística sector | Tinsa API — M3 plan Agencia |
| Ajuste por condición/antigüedad | Multiplicadores estándar del sector | Aprendido de transacciones reales del partner |

**Posición editorial:** cero scraping. Solo proveedores oficiales con contrato.

**Punto clave de arquitectura:** la interfaz de las MCP tools (firma de funciones, JSON Schema) **no cambia** al sustituir el proveedor sintético por Idealista/Tinsa. El agente no se entera. Es la garantía de evolución del Track 3.

## Pipeline ejemplo concreto

**Input al agente:**
```
Calle Mayor 5, Madrid, 28013
95 m², a_reformar, año 1965, reforma 35.000 €
```

**5 tool calls (3-5 seg total):**

1. `geocode_address({"address":"Calle Mayor 5","locality":"Madrid","postal_code":"28013"})`
   → `{lat: 40.4163, lon: -3.7055, neighbourhood: "Barrio de los Austrias", city_district: "Centro"}`

2. `find_comparables({"lat":40.4163, "lon":-3.7055, "province":"Madrid", "district":"Centro"})`
   → 8 comparables, `median_price_eur_per_m2: ~5500`

3. `estimate_market_value({"surface_m2":95, "median_price_eur_per_m2":5500, "condition":"a_reformar", "year_built":1965})`
   → `value_eur: ~375000`

4. `estimate_market_value({...condition:"buen_estado"})`
   → `value_eur: ~500000`

5. `compute_renovation_roi({"investment_eur":35000, "current_value_eur":375000, "post_reno_market_value_eur":500000})`
   → `{net_gain: 90000, payback_ratio: 3.57, recommendation: "muy_recomendado"}`

**Output al agente inmobiliario:**

> Zona: Barrio de los Austrias, distrito Centro de Madrid. Mediana de comparables 5.500 €/m².
>
> | Concepto | Valor |
> |---|---:|
> | Valor actual (a reformar) | 375.000 € |
> | Inversión reforma | 35.000 € |
> | Valor estimado post-reforma | 500.000 € |
> | Revalorización neta | **+90.000 €** |
> | Payback ratio | **3,57×** |
> | Recomendación | 🟢 **Muy recomendado** |
>
> Veredicto para el propietario: la reforma multiplica por 3,5 lo invertido en valor de tasación.

## Trazabilidad y honestidad

- Cada comparable lleva `source: "synthetic-mvp"`.
- El agente cita siempre el origen del dato en su respuesta.
- En la submission y vídeo se explica el camino de datos sintético → real.
- Cero claims falsos de tracción o de fuentes de datos.

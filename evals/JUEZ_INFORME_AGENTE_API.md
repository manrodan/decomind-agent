# Juez: «informe del agente» por API: Opus 5.5, Sonnet 5.5, GPT-6.1 Sol, GPT-6.1 Terra y Gemini 3.8 Flash

Fecha: 2026-11-08 (v2, con OpenAI). 5 viviendas de Benicàssim × 5 modelos, mismo prompt y mismo `precios_zona`.

Configuraciones probadas:
- **Claude** (`comparar.py`): `web_search_20260209`, `max_uses: 12`, effort `high`, sin dominios y sin reanudar `pause_turn`.
- **OpenAI**: Responses API + web search; 2-7 búsquedas.
- **Gemini**: se resume del juicio anterior (`JUEZ_INFORME_AGENTE.md`).

Método:
- Leí los 25 informes y sus `.json`, y crucé cada URL con las `fuentes`. En Claude son los resultados del buscador; en OpenAI son las anotaciones `url_citation`, una prueba más débil.
- Descargué con curl/WebFetch las 20 URLs que no son de idealista.
- Idealista da 403, así que lo comprobé por patrón e ID, por coincidencia entre ejecuciones y modelos, y contrastando los datos con Kelify/Habitaclia.
- Conté palabras sin la tabla y recalculé cierre, honorarios y puntuación.

**Correcciones a la v1 y al juicio anterior:**
- **Motor del 308:** no localizó la calle (`precision: locality`, confianza «baja»). Valora a nivel de código postal (2.981 €/m² notarial × 1,22). Que salga 3.628 €/m², igual que la media de la Curva, es casualidad. La referencia del motor para el 308 es débil.
- **62 de Opus:** «Riu Tajo, en La Parreta/Montornés» **es correcto**. El geocodificado del motor la sitúa en la Urb. La Parreta y pisos.com coloca la Av. de la Parreta en Montornés. Aun así, el motor (814 k, 2.808 €/m²) queda muy por encima de los 400-470 k de los cuatro modelos y de los 1.760 €/m² de oferta del barrio: hay que revisar el motor en chalets grandes.
- **Hechos de Gemini que el juicio anterior dio por inventados:**
  - **243** «reformada, vistas, trastero de 15 m²»: está en el anuncio de la propia vivienda en Habitaclia (hoy retirado).
  - **225** «no agencias, no negociable, Catastro/Registro»: está en su anuncio de Idealista 112693890, que citan los dos GPT.
  - **308** «bajada desde 250 k»: la encuentran también Opus y Sonnet.

  El fallo de Gemini sigue siendo inventar URLs, no los hechos.

## Opus y Sonnet

A = listados / con URL / URL de ficha / repetidas o inventadas / **confirmados**. D = punto medio del cierre ÷ motor · ÷ pedido.

| Informe | A | B. Prompt | C. Números | D · sin respaldo | E. Utilidad |
|---|---|---|---|---|---|
| 308 Opus | 6/6/0 (listados, avisado)/0 inv./0 | ✗ 678 pal.; ✗ salida 245 k dentro del cierre (235-250 k) | ✔ | 0,56 · 1,05. «Antes 250 k» como dato | Buena: posible 2.ª ficha/agencia |
| 308 Sonnet | 8/8/0/misma URL en 2 pares, sin avisar/0 | ✗ 640; «incumple la normativa» | ✔ | 0,59 · 1,11 | Buena |
| 170 Opus | 6/0 en tabla/0/0/2 (Kelify) | ✗ 612 | ✔ | 1,08 · 0,91. Encuentra el anuncio propio con 100 m² | Muy alta |
| 170 Sonnet | 8/8/0/0/3 (+ 398.999 € en Habitaclia) | ✗ 646 | ✔ | 1,05 · 0,89 | **Muy alta: el mismo piso con agencia** |
| 62 Opus | 8/8/1 retirada/0/1; fila de Catastro; parcela de 3.707 m² | ✗ 595 | ✔ exacto | 0,51 · 0,93 | Buena (Lion Capital) |
| 62 Sonnet | **VACÍO** (`stop: tool_use`) | — | — | — | Fallo |
| 225 Opus | 6/6/1 retirada (Wallapop)/0/0 | ✗ 581; bloque extra | ✔ | 0,87 · 0,76 | Alta |
| 225 Sonnet | 8/8/1 retirada/0/0; m² «~96 (Estimación)» | ✗ 544; se cuela «Voy a ver…» | ✔ | 0,91 · 0,79 | Media |
| 243 Opus | 8/8/4/0/**4** | ✗ 666 | ✔ | — · 0,87 | Alta |
| 243 Sonnet | 8/8/2/0/3 | ✗ 640 | ✔ | — · 0,90 | Alta |

## GPT-6.1 Sol y Terra (nuevo)

| Informe | A | B. Prompt | C. Números | D · sin respaldo | E. Utilidad |
|---|---|---|---|---|---|
| 308 Sol / Terra | Filtro previo con 1 URL (idealista 110620713, M.S. Gestión) | ✔ formato exacto del filtro | — | — (ver abajo) | Acierto probable: ahorra la llamada |
| 170 Sol | 5/5/**5**/0/3-4 (13.ª y 14.ª coinciden con Kelify; la 4.ª, 345 k, con Habitaclia; Korinto con el mismo ID que Terra) | ✔ 409 pal.; descuento −4 % «hipótesis» | ✔ ≈342 k ajustado −4 %; honorarios ✔; 6/10 ✔ | 1,11 · 0,94. Cita el anuncio propio de 100 m² (Kelify ✔) | Alta, con fichas que se pueden abrir de la 13.ª y la 14.ª |
| 170 Terra | 5/5/5/0/2 (Habitaclia en vivo ✔; Korinto) | ✔ 368 | ✔; 5/10 ✔ | 1,12 · 0,95. 100 m² ✔ | Media: **no ve los 3 hab. de su edificio**; argumentos genéricos |
| 62 Sol | 5/5/5 (pisos.com **desactivado**)/0/2 (Olivos en Habitaclia; pisos.com) | ✔ 405 | ✔; 6,5/10 ✔ | 0,53 · 0,96. **Su comparable de más peso (Olivos: 283 m², parcela de 400, 2006, 450 k) es casi seguro la propia casa con agencia**, sin aviso. Anuncio propio con ID de 7 dígitos (1606108), dudoso | Media |
| 62 Terra | 4/4/4/0/1; incluye parcela de 3.700 m² y Pueblo | ✔ 393; ✗ salida 449 k dentro del cierre (420-470 k) | ✔; 5/10 ✔ | 0,55 · 0,99. **Avisa de la posible duplicidad con Olivos** | Buena |
| 225 Sol | 3/3/3/0/1 (Mestre Segarra); Antonio Puerto es VPO, sin aviso | ✔ 411; <5 comparables, avisado | ✔; 3/10 ✔ | 0,96 · 0,84. **Lee el anuncio propio: no agencias, no negociable, local en Catastro** (como «declaraciones suyas») → «Descartar por ahora» | **Muy alta**: evita una llamada que el propietario prohíbe y prepara la entrada por lo documental |
| 225 Terra | 3/3/3/0/2 | ✔ 342 | ✔; 2/10 ✔ | 0,90 · 0,79. Lo mismo | Muy alta |
| 243 Sol | 3/3/3/**1 ID discrepante** (Ribalta 4 con 112246628; los otros 4 informes dan 112421379)/2 | ✔ 414 | ✔; 6/10 ✔ | — · 0,94. Lee el anuncio propio en Habitaclia (hoy retirado): reforma de 2021, vistas, **1 baño + aseo, no 2 baños** | Alta |
| 243 Terra | 5/5/5/0/3 (112421379 ✔; 105 m²/365 k y 120 m²/339 k coinciden con Opus/Sonnet) | ✔ 369 | ✔; 5/10 ✔ | — · 0,93. Habitaclia marca «sin parking» aunque la descripción lo incluye: lo pone en riesgos | Alta |

**Lo transversal de OpenAI:**
- **Calidad:**
  - **Todas las filas llevan URL de ficha**: 33. Ningún ID se ha demostrado inventado y 10 IDs se repiten entre Sol y Terra en ejecuciones independientes.
  - Tienen dos debilidades: 1 ID mal asignado y 1 comparable que es la propia vivienda.
  - Todos los informes quedan **por debajo de 500 palabras**, con «Estimación:» en todo.
  - **Buscan el anuncio de la propia vivienda en otros portales y sacan los hechos que deciden la captación** (225, 243, 170, 308). Ningún Claude lo hizo así.
- **Pegas:**
  - Dan 3-5 comparables (se piden 5-8).
  - El descuento lleva un motivo vago («hipótesis»).
  - Los argumentos son genéricos («filtrado de compradores, seguimiento de visitas») y el tono es más de informe que de compañero.
  - Las fichas de idealista **no las podemos comprobar por HTTP**.

### 308: ¿acierta el filtro previo?
No puedo abrir la ficha 110620713 (403) y no está indexada. Por indicios, lo cuento como **acierto probable, no confirmado**.

A favor:
- **«Es un particular» no viene del anuncio**: `comparar.py` lo añade a la ficha de las 5 viviendas.
- El único anuncio de José Bellido Mor con 120 m², 4 hab. y garaje a 230 k que han encontrado 4 modelos y el agente manual es de agencia.
- Opus vio ese 230 k en dos portales (Idealista + yaencontre, donde suelen publicar las agencias) con la misma rebaja.
- Nadie ha encontrado un anuncio de particular a 230 k.

En contra:
- En la calle hay 4-5 adosados casi iguales.
- Opus vio una versión con 4 hab. y otra con 5.

Si fuera otra casa, sería un descarte falso, aunque mitigado porque deja la URL para comprobarlo con un clic. Opus vio la misma pista y la dejó en «Riesgos» sin dar ninguna valoración menos. Para producción, el filtro debe enseñarse como aviso con enlace y un botón «es particular: valorar igualmente». Además, hay que pasar al modelo la URL/ID del anuncio y el tipo de anunciante que captura la extensión, para que compare por ID y no por características.

## Ganador por vivienda (5 candidatos)
- **308 → GPT (Sol = Terra), si se confirma el anuncio de agencia.** Si no se confirma, Opus.
- **170 → Sol.** Tiene fichas de la 13.ª y la 14.ª de su edificio y el aviso de los 100 m². Se le escapa el anuncio de agencia a 398.999 € que vio Sonnet.
- **62 → Terra, por poco.** Es el único que avisa de que su mejor comparable puede ser la propia casa. Las cifras de todos coinciden (400-470 k).
- **225 → Sol.** El dato que decide (el propietario rechaza agencias y el precio no es negociable) sale con la URL de su anuncio, y la valoración queda a 0,96 del motor.
- **243 → Terra, por poco, sobre Opus.** Tiene 5 fichas con el ID correcto y lee el anuncio propio. Opus tiene 4 fichas confirmadas pero no vio el anuncio propio.

Claude Opus queda segundo en 4 de las 5. Sonnet y Gemini no ganan ninguna.

## Veredicto con coste

| Modelo | Coste/informe | Tiempo | URLs de ficha | ≤500 pal. | Hechos clave del anuncio propio | Gana |
|---|---|---|---|---|---|---|
| Gemini 3.8 Flash | 0,04 $ | 54 s | 0 válidas de 25 | 5/5 | Sí, sin fuente | 0 |
| **GPT-6.1 Terra** | **0,10 $** | 35 s | 17 | 5/5 | Sí, con URL | 2 (+308) |
| **GPT-6.1 Sol** | **0,15 $** | 35 s | 16 | 5/5 | Sí, con URL | 2 (+308) |
| Claude Sonnet 5.5 | 0,60 $ | 91 s | 3 (1 vacío) | 0/4 | Parcial | 0 |
| Claude Opus 5.5 | 1,50 $ | 132 s | 6 | 0/5 | Parcial | 0 (2.º en 4) |

**Producción: GPT-6.1 Sol.** Es 10 veces más barato que Opus y 4 veces más que Sonnet, el doble de rápido, cumple el formato y es el que mejor encuentra el anuncio propio y los comparables con ficha. Terra (−33 % de coste) queda a la par en 62 y 243, pero en el 170 se le escapan los comparables de su edificio. La diferencia de 0,05 $ no merece arriesgar eso. **Claude Sonnet** queda como **respaldo** si OpenAI falla o se queda sin crédito (ya pasó con el cenital), con la configuración reducida de la v1 (`max_uses: 5`, dominios, effort `medium`; ≈0,25 $). Opus no compensa: su ventaja sobre Sonnet no se acerca a la de Sol sobre ambos.

**Antes de cambiar:**
1. Abrir en el navegador las 33 fichas de idealista citadas por GPT (5 minutos). Es la prueba que nosotros no podemos hacer por HTTP.
2. Repetir con 15-20 viviendas más. Con 5 casos, un 2-3 de diferencia no es concluyente.

### Configuración de producción
- **Responses API**, modelo `gpt-6.1-sol`, razonamiento medio.
- **Herramienta `web_search`** con:
  - `filters.allowed_domains`: idealista.com, fotocasa.es, habitaclia.com, pisos.com, kelify.com, yaencontre.com, indomio.es, realadvisor.es;
  - `user_location` en ES/Castellón;
  - **máximo 6 llamadas a herramientas** (`max_tool_calls`).
  - Hay que comprobar los nombres exactos en la documentación vigente.
- Pedir en `include` las fuentes completas de la búsqueda, no solo las anotaciones, para la lista blanca.
- **Prompt**:
  - pasar la URL/ID del anuncio y el tipo de anunciante;
  - «busca primero el anuncio de esta vivienda en otros portales y cita los hechos con su URL»;
  - «cada argumento debe apoyarse en un dato de la tabla o del anuncio»;
  - «excluye comparables que coincidan con esta vivienda en calle, m² ±5 %, parcela y año».

### Post-proceso imprescindible
1. Las URLs de la tabla deben estar en las fuentes; quitar `?utm_source=openai` y las citas duplicadas `([idealista.com](…))`.
2. Patrón de ficha por portal. GET a las que no son de idealista: retirada → fuera (pisos.com en el 62). Para idealista, mientras no haya un método verificado, enseñar «sin verificar» y deduplicar IDs.
3. **Detector de la propia vivienda**: misma calle o zona, m² ±5 %, parcela, año y precio ±3 % → fila fuera y aviso de «posible anuncio con agencia» (62).
4. Filtro previo y «Descartar por ahora»: siempre con la URL que lo justifica y el botón «valorar igualmente».
5. Coherencia: salida > techo del cierre (fallan Terra 62 y Opus 308), cierre ≈ media ajustada × (1 − descuento) ±10 %, honorarios 3 %, puntuación = suma, ≤500 palabras.
6. Alerta si el cierre se separa del motor más de un 25 %, enseñando la precisión del motor (en el 308 no localizó la calle).

### Coste con esa configuración
El coste de búsqueda crece con el contexto acumulado (cada búsqueda vuelve a leerlo todo). Por eso Claude, con 12 búsquedas, leía 105-468 k tokens, y OpenAI, con 5-7, lee 41-66 k.
- **Sol** ya está en ~0,15 $: entrada ~55 k × 2 $/M ≈ 0,11 $ (con ~7 k en caché), más 6 búsquedas ≈ 0,06 $, más salida ≈ 0,02 $. Con el tope de 6 llamadas y los dominios (menos páginas que leer) estimo **≈0,12-0,14 $ (−10/20 %)**. El ahorro grande ya está en haber cambiado de modelo.
- **Respaldo Sonnet reducido:** ≈0,25 $.
- **Total para 100 informes/mes:** ~13 $ con Sol, frente a 150 $ con Opus tal como está hoy.

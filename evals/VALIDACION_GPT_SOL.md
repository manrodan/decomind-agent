# Validación: GPT-6.1 Sol en 10 viviendas fuera de Benicàssim

Fecha: 2026-11-08. Prompt `prompt_agente_v2.md` (con «Reglas de evidencia»). Configuración de producción: Responses API, `web_search` con 8 dominios, ES, `max_tool_calls` 8, razonamiento medio. Coste medido: 0,18 $ (0,08-0,26) y 12-67 s.

Método:
- Leí los 10 informes y fichas.
- Crucé con un script cada URL contra `fuentes` y `citas`, y rehíce las cuentas.
- Busqué los 3 anuncios de agencia en la web.
- La única URL que no es de idealista (yaencontre, 167) da 403 tanto en WebFetch como en el buscador, así que no la pude abrir.

## Tabla por informe

A = filas / con URL de ficha / en `fuentes` / solo en `citas` / en ninguna. D = punto medio del cierre ÷ motor · ÷ pedido.

| Id · municipio | Veredicto | A | B-C. Prompt y números | D | Anuncio propio | E. Utilidad |
|---|---|---|---|---|---|---|
| 79 Castellón (Sensal) | Seguimiento | 5/5/2/3/0 | ✔ 415 pal., cuentas ✔. ✗ Salida de 245 k frente a 215 k pedidos («no subir»): contradictorio | **1,34** · 1,07 | No lo encuentra (la ficha es `manual`) | **Floja**: todas las filas tienen garaje y piscina frente a un «Piso» sin datos; queda +34 % sobre el motor |
| 134 Castellón | Descarte | URL de agencia: solo en `citas` | ✔ | — | Nomdedeu, 290 k | **Útil** (ver G) |
| 195 Vila-real | Ir a por ella | 5/5/**5**/0/0 | ✔ 405; 6/10 ✔; honorarios ✔ | 1,18 · 0,95 | ✔ particular «Medi», reformas (solo en `citas`) | **Alta** |
| 236 Vila-real | Seguimiento | 5/5/**5**/0/0 | ✔ 403; 6/10 ✔ | **1,29** · 0,99 | Solo en el listado: «entre particulares, sin comisiones» (lo marca sin confirmar) | Media-alta |
| 188 Oropesa | Seguimiento | 3/3/3/0/0 (avisa de que son <5) | ✔ 427; 1.803 × 189 × 1,05 × 0,95 ✔; 5/10 ✔. «Piscina privada» sin dato | 0,85 · 0,95 | ✔ particular Raquel, «sin comisión» | Media-alta |
| 238 Onda | Seguimiento | 5/5/1/4/0 | ✔ 413; 6/10 ✔. ✗ Salida = techo del cierre (170 k) | 0,79 · 0,71 (**0,96 sobre los 170 k reales**) | ✔ Esther: **ahora 170 k, antes 230 k** | **Muy alta**: el precio de la ficha está desfasado |
| 168 Almassora | Descarte | URL de agencia: solo en `citas` | ✔ | — | P&M, 165 k | Útil con clic (ver G) |
| 211 Burriana | Seguimiento | 4/4/0/2/**2** | ✔ 429; 5,5/10 ✔. ✗ 2 filas con ID de ficha visible y cita a un listado | **1,40** · 0,92 | ✔ JLD: 90 m² de vivienda + 47 de terraza, 3.000 € de muebles | Media |
| 167 Nules | Descarte | URL de yaencontre en `fuentes` ✔ | ✔ | — | HogarAbitat, ref. 118CAS120 | **Útil** (ver G) |
| 298 Borriol | Seguimiento | 4/4/4/0/0, todas como «referencia» ✔ | ✔ 377. ✗ **No da rango**: el prompt pide valorar con precios_zona y avisar | — | ✔ José Luis: inquilinos, ubicación Benadresa | **Floja** como valoración; buenos hechos para la llamada |

Ratios (6 valoraciones con rango):
- **Cierre ÷ motor**: 0,79-1,40, mediana 1,24. 3 de 6 se separan más de un 25 % (79, 236, 211).
- **Cierre ÷ pedido**: 0,92-1,07, mediana 0,95.

## F. Reglas de evidencia

- **URL de ficha en cada fila: 31 de 31**, todas con patrón `idealista.com/inmueble/<9 dígitos>/`. Ninguna es de listado sin marcar, salvo las 2 del 211.
- **¿Hay URLs inventadas?** Ninguna está demostrada.
  - 20 de 31 están en `fuentes`.
  - 9 están solo en `citas` (79 ×3, 238 ×4, 211 ×2), igual que el anuncio propio en 195 y 211 y los anuncios de agencia en 134 y 168.
  - Causa probable: `validar.py` solo guarda `action.sources` de las acciones `search`. **No guarda la `action.url` de `open_page`/`find_in_page`**. Ejemplo: en el 134 hay 3 llamadas y 12 fuentes, y cita una ficha que no está entre ellas.
  - Consecuencia: la lista blanca tal como está rechazaría 13 URLs probablemente buenas.
  - **El 211 sí incumple la regla.** En 101043043 y 111432758 el ID visible no está ni en `fuentes` ni en `citas`, y la anotación apunta a un listado. Debían ir como «referencia» y no entrar en la media.
- **Propia vivienda como comparable: ningún caso claro.** La excluye de forma explícita en 6 informes.
  - Hay un posible duplicado en el 195: **Pius XII 42** tiene 90 m² (los útiles de la vivienda), 3.ª sin ascensor, 3 hab., reformado y 115.000 €, frente a 114.900 €. Va en la tabla, aunque fuera de la media.
  - En ese mismo informe, el modelo avisa de que la fila de 85 m² a 114.300 € puede ser un duplicado.
- **Descuento con motivo concreto: 6 de 6** (rebajas del 5-6 % vistas en Sequieta, Navarra o Río Nilo, la rebaja de 60 k del propio anuncio, competencia con nombre). Todos son del 3-5 %, salvo el 238 (3-8 %).
- **Argumentos apoyados en un dato**: casi todos llevan cita. Excepciones:
  - 188 llama «piscina privada» a lo que la ficha solo describe como «Piscina», con 90 m² de parcela;
  - en 79 y 238 hay argumentos genéricos.

## G. Descartes por «posible anuncio de agencia»

| Id | Coincidencia | URL | Solidez |
|---|---|---|---|
| 134 | Mismo número de calle (S. Francesc/S. Francisco 83), 236 m², 5 hab., 3 baños; 290 k frente a 295 k (−1,7 %) | ✔ idealista 113000181 | **Sólida.** El ID es posterior al 112982001, que se capturó el 4-nov, y la captura del 134 es del 7-sep: es un anuncio **nuevo** de agencia. Lo más probable es que la casa haya pasado a una agencia (¿o es la del propio usuario?) |
| 168 | Mismo número (Catalans 30), 103 m², 3 hab., 2005; 165 k frente a 160 k (+3 %) | ✔ idealista 112109424 | **Media-alta.** El buscador confirma un anuncio a 165 k (103 m², 3 hab., garaje) y otro en Fotocasa en «Camí Catalans, 30». Pero el 30 puede ser el portal de toda la urbanización de adosados iguales, y no comprueba los inquilinos. El propio modelo lo advierte |
| 167 | 102 m², 4 hab., 1 baño, 6.ª con ascensor, **120.000 € exactos**; falta el n.º 16 | ✔ yaencontre (en `fuentes`) | **Sólida en características.** El formato 118CAS120 coincide con las referencias de HogarAbitat en Trovimap (118VAL130, 118CON114). El sufijo 112590329 parece un ID de idealista de septiembre, como la captura (16-sep). Hipótesis: es el mismo anuncio que capturó el agente |

Los tres descartes dan la URL, dicen «posible» y advierten de que puede haber casas casi iguales. **Ninguno es especulativo.**

Los informes que afirman «particular» (195, 188, 238, 211 y 298) lo hacen siempre **con la URL de su anuncio** y el nombre del anunciante. El 236 dice que lo vio solo en un listado y no lo confirma, y el 79 dice que no lo encontró. **No hay ninguna afirmación sin prueba.**

## H. Tasa de informes útiles

**7 de 10 se pueden llevar a una captación sin vergüenza:**
- tres descartes bien fundados (134, 167 y 168, este con un clic de verificación);
- cuatro valoraciones con fichas que se pueden abrir y hechos del anuncio propio (195, 238, 188, 236).

**Uno es aprovechable con reservas (211).** Tiene buenos hechos del anuncio propio, pero 2 filas sin respaldo y queda a 1,40 del motor.

**Dos son flojos:**
- **79**: no encuentra el anuncio, los comparables son de un segmento superior y la salida contradice el pedido;
- **298**: no da rango.

## Veredicto

**Se confirma GPT-6.1 Sol para producción**, con los cambios de abajo.

En terreno nuevo mantiene lo que lo hizo ganar:
- formato ≤500 palabras (377-429);
- URL de ficha en todas las filas;
- busca el anuncio propio y saca el hecho que decide la captación: rebaja a 170 k, «sin comisiones», 47 m² de terraza, inquilinos, agencia nueva.

No he visto ninguna URL inventada demostrable. Nada de esto cambia el orden frente a Claude.

**Fallos sistemáticos y su arreglo:**

1. **Lista blanca incompleta (es fallo nuestro).**
   - Guardar también `action.url` de `open_page`/`find_in_page` en `validar.py` y en producción.
   - Lista blanca = sources ∪ páginas abiertas.
   - Post-proceso: si el ID visible de una fila no coincide con la URL de su anotación (211), la fila pasa a «referencia» y sale de la media.
2. **El cierre es la oferta −3/5 %.**
   - Cierre ÷ pedido queda en 0,92-1,07, pero cierre ÷ motor va de 0,79 a 1,40, y en los pisos urbanos sale por encima del motor (1,18-1,40).
   - Escoge comparables del segmento alto: en el 79 todos tienen garaje y piscina.
   - **Prompt**: pasar el valor del motor (Notariado + Catastro) y su precisión como dato de cierre, y exigir que explique cualquier separación de más del 20 %.
   - **Post-proceso**: alerta si la separación pasa del 25 %.
3. **Coherencia de la salida.**
   - Comprobar salida > techo del cierre (falla el 238).
   - Si el pedido < cierre, no proponer una salida por encima del pedido sin decirlo (79).
4. **Sin rango (298).** Prompt: «Da siempre un rango; con <3 comparables, ensánchalo (±15 %) desde precios_zona y márcalo como aproximado». Hoy se niega.
5. **Descartes.**
   - Enseñarlos como aviso con la URL y un botón «es particular: valorar igualmente».
   - **`listings.json` no guarda el ID ni la URL del anuncio capturado por la extensión.** Guardarlos y pasarlos al modelo para comparar por ID (el 167 se resolvería al momento) y para fechar con el ID: un ID posterior a la captura significa «pasó a agencia» (134).
6. **Detector de duplicados.** Fila con m² ±5 % (construidos o útiles), mismas habitaciones y planta y precio ±3 % → fuera, aunque cambie la calle (Pius XII en el 195).
7. **Limpieza.** Quitar `?utm_source=openai` (8) y las citas duplicadas `([idealista.com](…))` (69).

**Aparte:**
- En 188 y 211 hay **9** llamadas con `max_tool_calls` 8: hay que revisar si el tope cuenta las aperturas.
- Las fichas de idealista siguen sin verificarse por HTTP. Antes de lanzar, hay que abrir las 31 en el navegador.

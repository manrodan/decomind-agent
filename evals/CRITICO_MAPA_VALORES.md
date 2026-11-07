# Veredicto: ACEPTAR CON CAMBIOS — el mapa de valores no empeora el backtest, es mejor fuente por construcción y con casi el doble de cobertura; antes de desplegar, tres arreglos pequeños en `mcp_servers/zona_valor/server.py` (caché que vuelve a descargar, huecos de polígono, timeout) y, como seguimiento, un guardarraíl para ciudades grandes.

Crítico independiente, 2026-11-07. Datos: 132 pares (motor de hoy vs motor con mapa), filtros del encargo; 126 sin duplicados (6 anuncios repetidos: #78/#94, #142/#166, #58/#101…). Solo 106 tienen precisión `street` (los 26 `locality` no reciben ajuste en ninguna pasada). Scripts: `scratchpad/critico_mapa.py` y `scratchpad/probe_mapa.py` (sonda en vivo).

## A. Criterio (1): no empeora — SE CUMPLE (mejora pequeña y no significativa en MAD; borderline en % fuera)

| | fuera de [0,75-1,0] | MAD log | mejora / empeora / igual (distancia al centro 0,875) |
|---|---|---|---|
| todos (n=132) | 73,5 → 68,2 % · Δ −5,3 pp, IC95 bootstrap [−10,6, −0,8] | 0,251 → 0,240 · Δ −0,011, IC95 [−0,042, +0,040] | 49 / 31 / 52 · signos p=0,057 · Wilcoxon z=−1,89 p=0,058 |
| sin duplicados (n=126) | 72,2 → 67,5 % · IC95 [−9,5, 0,0] | 0,249 → 0,239 (n.s.) | 48 / 29 / 49 · signos p=0,040 · Wilcoxon p=0,034 |

Lectura: el % fuera baja de forma apenas significativa (el IC95 roza el cero; p≈0,05 en los tests apareados); la MAD **no cambia de forma significativa** (P(ΔMAD>0)=0,47). No hay empeoramiento global. Fuera→dentro 9, dentro→fuera 2. Gradiente aplicado en 92 de 106 casos `street` (81 mapa + 11 ponencia) frente a 49 antes.

Por municipio (n ≥ 10; mejora/empeora en los que cambian; bootstrap de ΔMAD):

| municipio | n | fuera | MAD | mejora/empeora | P(ΔMAD>0) |
|---|---|---|---|---|---|
| Castellón | 23 | 70 → 70 % | 0,229 → 0,264 | 6 / 6 | 0,39 |
| Burriana | 15 | 80 → 80 | 0,145 → 0,156 | 6 / 1 | 0,44 |
| Vila-real | 15 | 73 → 60 | 0,147 → 0,159 | 6 / 6 | 0,71 |
| Oropesa | 14 | 100 → 100 | 0,159 → 0,149 | 5 / 3 | 0,31 |
| Benicàssim | 13 | 69 → 54 | 0,338 → 0,487 | 2 / 6 (sin dup. 2 / 5; signos p=0,29) | 0,55 |
| Onda | 13 | 62 → 62 | 0,124 → 0,167 | 5 / 5 | 0,86 |
| Almassora | 12 | 67 → 50 | 0,150 → 0,143 | 6 / 1 | 0,48 |

Ningún municipio empeora de forma sistemática. Los dos que preocupaban:
- **Castellón**: la MAD sube porque la mediana del municipio se mueve (0,72 → 0,80) al corregir al alza tres anuncios muy infravalorados (#79 0,64→0,80, #182 0,40→0,50, #126 0,42→0,51, todos coherentes con lo pedido) mientras 11 anuncios no cambian. Los 6 «empeora» son todos ≤ 0,14 en |Δlog| y 3 de ellos (#229, #150, #107) son el mismo ámbito MV1081 (antes R41 −18 %, ahora −7,5 %): el residuo pedido/Notariado de esos pisos es −6…−11 %, o sea el mapa está **más cerca de lo que pide el anuncio** que la ponencia; quedan «peor» solo porque el centro del margen es 0,875 (acaban en 0,98-1,04).
- **Benicàssim**: la subida de MAD la causan **dos anuncios** (no un patrón): el pareado duplicado #78/#94 (1,28 → 1,49) y el chalet #62 (1,66 → 1,81). Ambos unifamiliares con residuo −38 % / −60 %: la base del motor ya iba un 28-66 % por encima de lo pedido antes de cualquier ajuste; la ponencia les restaba −12 %/−9 % **desde zonas U27/U34** (códigos no residenciales que el propio `_pick_fallback_zone` evita) — una corrección accidental, no una señal. El mapa dice «zona media de villas» (+2 % / −0,2 %), que es lo que es. Los otros tres (#71, #108, #170) cambian ≤ 0,05. El problema de Benicàssim es la base unifamiliar, no el gradiente.

## B. ¿Tiene sentido el gradiente? Sí

- 12 mayores cambios: **9 coherentes** con el residuo pre-ubicación (log pedido/m² ÷ valor/m² antes del ajuste), 3 contrarios y 2 de esos 3 son el duplicado #78/#94 (el otro, #229, residuo −9 % vs ajuste −7,5 %: casi neutro). Todos los que cambian (n=80): 46 coherentes / 34 contrarios (el residuo lleva también el error hedónico y la sobrevaloración del vendedor, así que 58 % no es malo).
- **Ningún caso** en que el mapa diga |≥ 20 %| y lo pedido vaya al revés (8 casos con |≥ 20 %|, 3 al tope ±30 %).
- corr(log gradiente, residuo) = **0,53 (n=81)** con el mapa frente a **0,31 (n=49)** con la ponencia (misma pasada A); confirma el 0,55 vs 0,34 de `CATASTRO_MAPA_VALORES.md`. Pendiente OLS 1,67 (ponencia: 0,67): la elasticidad 0,5 se queda **corta** con el mapa — conservador, bueno para «no empeorar»; recalibrar (≈0,7-0,8) solo con cierres reales.
- Criterio (2) cumplido: compraventas firmadas frente a valor IBI, 81 vs 49 anuncios con gradiente, codigos de clase piso/unifamiliar respetados (18 pisos + 22 unifamiliares sin gradiente en B por clase distinta/sin ámbito/precisión).

## C. Revisión del código — sin fallos de valor, tres defectos operativos (confirmados en vivo)

Correcto: clase por `Ptipo1`/`Ptipo2` con tipologías reales («Vivienda colectiva», «unifamiliar aislada/pareada», «en hilera»; un ámbito de Benicàssim 2027 trae tipología «0411» y cae como sin dato, 1/26); sin `property_type` (Dossier ROI) no se pide nada y la ponencia sigue igual; año: `anyoZV=2027` ya existe (ejercicio 2026, 26 ámbitos; el 2026 tiene 30: **los códigos cambian**); HTML → vacío → año anterior; 5xx/timeout → `error` → ponencia, y el engine solo marca `catastro_caido` si fallan ambas (correcto); tipos de campo (`val_tipo_m2` float, `num_inmuebles_uso_v` int); el tope ±30 % duplicado es redundante, no dañino (media geométrica de dos valores acotados queda acotada); tests 7/7 en verde; `app.py` es `async def` llamando a código síncrono → un solo hilo, no hay carrera en el dict.

Defectos:
1. **Caché que vuelve a descargar** (`_mapa_del_punto`): solo acierta si el punto cae **dentro** de un polígono cacheado. Playa, borde, ámbito gris sin dato (80 de 678 en Madrid), mar o foral → descarga cada vez. Reproducido: 4 llamadas en Benicàssim = 3 descargas; Bilbao = 2 GET (2027 y 2026, 42 B) por valoración, nunca cacheados. En Madrid cada fallo son **8 MB y 3,2 s** (el «~400 KB» del encargo es Benicàssim; Valencia 2,6 MB/1,3 s).
2. **Huecos ignorados** (`_zona_de_feature` solo guarda el anillo exterior; `_zona_del_punto` devuelve el primer polígono que contiene el punto): un ámbito-isla dentro de otro recibe el módulo del envolvente si este va antes en la lista. Madrid 25 polígonos con huecos, Valencia 29, Benicàssim 4. Error acotado a ±30 % pero real.
3. **Tiempo**: `_MAPA_TIMEOUT` 25 s por año × 2 años + cadena de la ponencia (15 + 40 + 8 s) supera de largo los 60 s de Cloud Run si Catastro va lento (antes el peor caso ya era ~63 s; ahora +50 s). PIP en sí es barato (Madrid: dentro <1 ms, fuera 13 ms, fuera + anillos 309 ms; 0,3 MB en memoria por municipio parseado).

Menores: HTML se trata como «sin ámbito» silencioso mientras un 5xx se marca `error` (incoherente con «fuente caída = no hay informe»; el doc vio 3 HTML seguidos); `_mapa_baseline` pondera el producto `Ptipo2` con el n total del ámbito (hay `num_inmueble` por producto; 17 ámbitos con 2 productos en Madrid).

## D. Riesgos que el backtest no ve

- **Ciudades multi-CP (Madrid, Valencia)**: baseline municipal con Notariado por CP = doble cuenta de la ubicación que el CP ya captura (igual que la ponencia, pero ahora con cobertura total). En Madrid 81 de 474 ámbitos de pisos (17 %) saturan al tope ±30 % y p10/p90 = 0,75/1,30 (Valencia 11/127); el centro (Sol) sale 6.140 vs base 3.980 → +24 % sobre un CP ya caro. El backtest solo tiene Castellón (6 CP, 23 casos, 6/6) — no valida esto.
- **Forales** (País Vasco, Navarra): 0 ámbitos, 2 GET perdidos por valoración; sin cambio de valor (cae a ponencia → nada → sección censal).
- **Códigos de zona**: `zone_code` «MV238» de 2027 no coincide con «MV2xx» de 2026 ni con «R23»; nada en `decomind-partner-api` lo usa como clave (`zona_precio.py` lee solo `gradient`), pero la app lo enseña: `ValuationPage.jsx:1413/1426` «Catastro, zona de valor MV1076» y `valuation_copy.py:167-171` «se usa la zona de valor del Catastro» — texto ahora inexacto (es el mapa de valores de referencia).
- Golden «12 iguales con el interruptor apagado» no re-ejecutado por mí (sin red/tiempo); plausible por el diff (la rama `ZONA_VALOR_MAPA=0` reproduce el código anterior línea a línea).

## Cambios

Antes de desplegar (≈1 h, todo en `server.py`):
1. Caché: recordar por municipio su bbox (unión de polígonos + margen) y resolver contra la caché con `_zona_con_respaldo` antes de descargar; cachear negativos (foral/mar) por punto redondeado a 3 decimales con TTL.
2. Huecos: guardar todos los anillos y en `_zona_del_punto` exigir «dentro del exterior y fuera de los huecos» (o elegir el polígono de menor área entre los que contienen el punto).
3. `_MAPA_TIMEOUT` 25 → 10 s.

Seguimiento (no bloquea):
4. Guardarraíl para municipios con > ~100 ámbitos (tope ±15 % o elasticidad 0,35) hasta pasar un backtest con anuncios de Valencia/Madrid; alternativa: baseline ponderada de los ámbitos a < 2 km (escala CP).
5. HTML: 1 reintento y luego `error=True` (coherente con 5xx).
6. Textos: «ámbito del mapa de valores» cuando `zone_source == "mapa_valores"` (app y `valuation_copy.py`), o esconder el código.
7. Ponderar `Ptipo2` con `num_inmueble` del producto; recalibrar la elasticidad solo con cierres reales.

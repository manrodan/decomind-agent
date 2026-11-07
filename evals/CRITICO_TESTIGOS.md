# Veredicto: RECHAZAR (en su forma actual, como capa que mueve el valor)

<!-- Agente crítico independiente, 2026-11-07. Cálculos propios sobre scratchpad/bt_zona.json (n = 135, sin los 5 sucios) y las 96 cachés de testigos; scripts en scratchpad/critico/an1-an4.py. -->

**Resumen.** La capa de testigos baja el «% fuera» de 72,6 % a 68,1 % (−4,4 pp), pero esa diferencia no se distingue del ruido (IC95 bootstrap de la diferencia: −1,5 a +11,1 pp; McNemar 13 entran / 7 salen, p = 0,26; Wilcoxon sobre la distancia al margen p = 0,25). La dispersión no cambia (MAD del log ratio 0,262 → 0,261). Cuando actúa (84 casos) acerca el valor al centro del margen en 49 y lo aleja en 35: poco mejor que una moneda. Y he encontrado cuatro fallos de implementación que deforman el resultado (filtro de calle que borra todos los testigos, sujeto que se cuela con ±2 %, «techo» con n = 2 que hunde un 47 %, fuentes que son páginas de listado ordenadas por precio). Ninguna combinación de parámetros que probé (cota, K, N_ANCLA, descuento, con/sin techo) saca el % fuera del rango 65-70 %: con esta métrica y esta muestra la capa **no demuestra** mejorar la precisión. Puede valer como información para el agente (los 5-8 anuncios de su zona, con aviso cuando lo pedido está muy por encima), pero no como segunda ancla del valor hasta corregir lo de abajo y, sobre todo, calibrar con cierres reales.

## A. ¿Reduce el % fuera? ¿Es ruido?

| capa | mediana | p10-p90 | fuera | >1 | <0,75 | MAD log | p90−p10 log |
|---|---|---|---|---|---|---|---|
| motor | 0,779 | 0,49-1,29 | 72,6 % | 28,1 % | 44,4 % | 0,250 | 0,966 |
| + zona | 0,771 | 0,50-1,25 | 72,6 % | 26,7 % | 45,9 % | 0,262 | 0,925 |
| + zona + testigos | 0,789 | 0,50-1,20 | 68,1 % | 23,7 % | 44,4 % | 0,261 | 0,874 |

- Cambian 84 de 135 filas. Test de signos sobre |log r − log 0,875|: 49 mejoran, 35 empeoran, p = 0,16. Sobre la distancia al margen [0,75, 1,0]: 39 mejoran, 29 empeoran, p = 0,27. Wilcoxon: p = 0,13 y 0,25.
- McNemar del «fuera»: 13 fuera→dentro, 7 dentro→fuera, p = 0,26. Bootstrap (10 000): % fuera zona IC95 65-80, testigos 60-76; diferencia IC95 **−1,5 a +11,1 pp**, P(diferencia ≤ 0) = 0,10.
- Comparado con el motor a pelo: 17 entran, 11 salen, p = 0,34. La capa de zona (ya en prod) frente al motor: 8 / 8, p = 1,0.
- Casi toda la «mejora» es por arriba: >1 baja de 26,7 % a 23,7 %; el <0,75 no se mueve (45,9 → 44,4 %).

## B. ¿Mejora la dispersión?

No. MAD del log ratio 0,262 → 0,261 (IC95 de la diferencia −0,03 a +0,07). IQR log 0,53 → 0,45 y p90−p10 log 0,925 → 0,874 mejoran algo, pero el IC95 del p90−p10 incluye 0 (−0,06 a +0,15). La media de |log r − log 0,875| pasa de 0,313 a 0,305 (IC95 −0,015 a +0,030). Solo mueve ligeramente la mediana (0,771 → 0,789).

## C. ¿Dónde empeora?

Grupos donde sube el % fuera: Almassora piso (4→5 de 8), Benicàssim chalet (1→2 de 2), el Grau piso (3→4 de 6), Vila-real adosado (0→1 de 1). Los 7 dentro→fuera son casos sueltos, no un sesgo de municipio, pero **tres son fallos de implementación**, no de mercado:
- **132 Vila-real adosado** 0,85 → 0,45: «techo» con **n = 2** (mediana de dos anuncios a 768 €/m²), −47 %. Igual 126 el Grau: 0,42 → 0,22 con n = 2 (−48 %). El techo con 1-3 anuncios solo puede bajar, nunca subir, y sin cota: asimétrico y frágil.
- **150 y 229, el Grau piso**, 80 m²: dos búsquedas del mismo distrito dan mediana 1 242 €/m² (tramo 60) y 2 133 €/m² (tramo 80); uno baja −25 % y el otro sube +25 %, los dos saturan la cota en sentidos opuestos. Es la señal de que los testigos del Grau son ruido (IQR/mediana 0,74 en una, 0,07 en la otra).
- 212, 98, 282 (Almassora/Castellón pisos, −8 a −12 %) y 62 (Benicàssim chalet +11 %) son discrepancias legítimas de 10 % que cruzan el margen por poco.

## D. Circularidad: ¿se cuela el propio anuncio?

Sí, por dos vías, y además el filtro de calle se pasa de frenada:
- **Se cuela.** Con la regla actual (precio ±2 % y m² ±5 %) quedan **21 filas** con un testigo a precio ±5 % y m² ±10 % (o precio idéntico). Varios son con casi toda seguridad el sujeto tras una bajada de precio: 87 Benicàssim chalet pedido 795 000/214 m², testigo 765 000/214 m² «Urbanización Montornés» (−3,8 %); 62: 470 000/292 vs 449 000/290; 253: 175 000/114 vs 170 000/115; 105: 239 900/220 vs 230 000/220. Como la mediana es robusta y n ≈ 7-9, el efecto en el agregado es pequeño (re-simulando con exclusión laxa el % fuera sigue en 68,1 %), pero con n = 4-5 un sujeto colado pesa.
- **Borra de más.** El filtro «misma calle» (subcadena ≥ 4 letras) elimina TODOS los testigos cuando la zona del anuncio es la propia calle: **194 Almassora** («Don Juan de Austria», 7 de 7 excluidos → «sin_anuncios»), **286 Burriana** («Zona Piscinas», 7 de 8), **287 Castellón** (9 de 9). Y en **58/101** (chalet Castellón, Gran Vía de Tàrrega) tira el mejor comparable (750 000 €/270 m², misma vía, 2 778 €/m²), deja n = 3 y la capa no puede subir el valor. De los 105 «excluidos» del informe, 23 son estos tres borrados totales.
- El €/m² pedido del sujeto queda en el **percentil 65** de sus propios testigos (40 por encima de la mediana, 22 por debajo, n ≥ 4): los anuncios captados piden por encima de su zona, y la capa, que ancla a mediana × 0,885, devuelve por construcción ratios ≈ 0,78. Con esta métrica, eso es a la vez lo que la hace «mejorar» y lo que la invalida como prueba.

## E. Calidad de los testigos (96 cachés, 686 anuncios)

- Portales reales: Idealista 468, Habitaclia 120, Fotocasa 55, pisos.com 43. Superficie dentro del 70-130 %: 0 violaciones. Duplicados exactos (precio+m²): 0 (los filtra el código). Mediana 8 anuncios por búsqueda; 2 búsquedas vacías.
- **647 de 686 URLs son páginas de listado, no fichas** (`/venta-viviendas/<muni>/<zona>/con-pisos/`); 107 de ellas con `?ordenado-por=precios-asc|desc`: el modelo lee los extremos baratos (69) y caros (38) de la zona, no una muestra. La «verificación cifra a cifra» garantiza que precio y m² están en el texto de Google, no que exista ese anuncio ni que se pueda abrir.
- Sin homogeneizar: 17 «obra nueva» y 17 «para reformar» mezclados en la misma mediana; 11 anuncios «alquilado / en rentabilidad» (venta con inquilino, descuento típico 15-25 %). Mismo inmueble en dos portales con m² distintos pasa el filtro de duplicados (62: 450 000/290 y 470 000/292).
- Dispersión: IQR/mediana de los testigos, mediana 0,27, p90 0,54; Bellreguard max/min = 9,1 (24 000 €/103 m² frente a 264 990/125). Burriana playa chalets: 1 241-4 452 €/m² con 3 adosados entre 9 «chalets».
- Solo 14 de 135 anuncios traían zona; en 87 la zona de los testigos es el distrito que adivina `buscar_zona` por la calle (el propio código dice que «falla a menudo»): si el distrito es otro, los testigos son de otra zona.

## F. Tope «firmado < pedido» en Benicàssim (170, 295)

No es la cota del ±25 %: el ancla **sin cota** da 0,472 (170) y 0,564 (295), igual que con ella. Los 8-10 testigos de «Pueblo» (80-100 m²) piden 1 874-3 300 €/m², mediana 2 400; el informe de Idealista da 2 173 €/m² al distrito; el anuncio 170 pide **4 688 €/m²** (1,9× la mediana de sus testigos) y el 295, 3 750. Dos fuentes independientes coinciden y lo anómalo es el precio pedido o el distrito asignado (sin dirección no puedo distinguirlo). En los 14 casos con tope, los que piden ≤ 1,05× la mediana de testigos (78, 94, 225, 261, 207, 77, 121) acaban en 0,79-1,05; los que piden ≥ 1,5× (87, 170, 295, 228, 231) se quedan en 0,45-0,56 hagas lo que hagas. Lo que sí sobra es **apilar dos descuentos «firmado < pedido»**: el tope multiplica por 0,885/ρ y luego el ancla vuelve a aplicar 1 − 0,115 sobre la mediana; con n ≥ 4 el ancla debería partir del valor de zona **sin tope** (el tope solo cuando no hay testigos). Efecto en 170: 0,48 → 0,50, marginal.

## G. Casas al 0,41-0,45

Tampoco es la cota: de los 19 casos con r < 0,55 tras testigos, en todos el €/m² pedido es **1,5-4,2× la mediana de sus testigos** (58/101: 1 946 vs 981; 142/166: 3 801 vs 2 572; 155: 4 190 vs 1 547). Lo que bloquea a 58/101 es el filtro de calle (D) + n = 3 → solo techo; a 287, el borrado total; a 142/166 la cota no satura (+17 %). Con cota 0,35 o sin cota el % fuera queda igual (68,1 / 68,9 %) y la MAD no mejora. Una cota mayor con n alto y dispersión baja es razonable en teoría, pero aquí no hay ningún caso al que le sirva: no la cambiaría sin cierres reales.

## H. Coste y tiempo

Búsqueda de testigos sola: mediana **33,5 s, p90 46 s, máx. 107 s** (cachés), 2-9 consultas de Google por llamada (1 petición con grounding por valoración: con 2 clientes + admins no llega ni al 10 % de las 5 000 gratis). El problema es el flujo: en 87 de 101 valoraciones no hay zona del anuncio y los testigos se lanzan **después** de `buscar_zona` (39-95 s + extracción), en serie: 125 + 20 + 125 + 20 s de techos = 290 s de peor caso, por encima del corte de 230 s de Azure (ver nota del techo de 230 s). Típico: +35-50 s sobre los 40-60 s actuales. No es aceptable en síncrono sin paralelizar o sin pasar a asíncrono; la caché de 7 días por zona|tipo|tramo solo salva la segunda valoración de la misma zona.

## Cambios concretos (requisito para volver a evaluar)

1. `excluir_sujeto`: la regla de calle solo si la calle del sujeto **no** es la zona buscada y nunca si elimina > 50 % de los testigos (en ese caso excluir solo por precio+m²). Tolerancia del sujeto: precio **±5 %** y m² **±10 %** (hoy ±2 % / ±5 %).
2. Techo con 1-3 anuncios: **quitarlo** (o exigir n ≥ 3 y cota −15 %). En la simulación «sin techo» el % fuera baja a 67,4 % y la MAD a 0,252, y desaparecen los −47 % de 132 y 126.
3. Con n ≥ N_ANCLA, aplicar el ancla sobre el valor de zona **sin tope_pedido**; el tope solo cuando no hay testigos.
4. Búsqueda: pedir fichas (`/inmueble/`), excluir «alquilado/en rentabilidad» y «obra nueva» salvo que el sujeto lo sea; descartar testigos fuera de [p25 − 1,5·IQR, p75 + 1,5·IQR]; **no** usar páginas ordenadas por precio.
5. Flujo: lanzar testigos en paralelo con `buscar_zona` también sin zona del anuncio (buscar con el municipio y refinar si llega distrito), o hacerlos asíncronos; techo de la llamada de testigos 60 s.
6. En el informe, mientras no haya cierres: mostrar los testigos y un aviso «lo pedido supera el p75 de los anuncios de la zona» (30 de 64 con n ≥ 4 aquí; 12 superan 1,5× la mediana), sin mover el valor. Reevaluar con el ratio valor/cierre de `property_outcome` cuando haya ≥ 30 ventas.

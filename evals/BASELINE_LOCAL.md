<!-- Generado por evals/backtest_local_motor.py (paso 1, 226 anuncios) + evals/backtest_local_zona.py (paso 2, muestra de 140) + scratchpad bt_report.py. Datos: tabla property de producción exportada el 2026-11-07 (sin datos personales). Criterio de cordura, no de precisión: lo pedido no es lo firmado. -->

# Backtest local · zona y testigos (2026-11-07)

Muestra estratificada: 140 anuncios captados (≤15 por municipio, mitad casas). Excluidos 5 con datos sucios (precio < 30 k€ o ratio motor fuera de [0,2, 3]): #66 benicassim 800€/64m² r=131.625, #68 benicassim 2000000€/120m² r=0.154, #161 oropesa del mar 20000€/40m² r=5.778, #69 torreblanca 820000€/45m² r=0.092, #259 villavieja 140000€/373m² r=3.226

Métrica: ratio valor/precio pedido. «Fuera» = fuera de [0,75, 1,0]; «>1» = valoración por encima de lo pedido. Mediana (p10-p90).

## Global

| capa | mediana (p10-p90) | fuera | >1 |
|---|---|---|---|
| motor | 0.78 (0.48-1.32) | 73 % | 28 % |
| + zona | 0.77 (0.49-1.26) | 73 % | 27 % |
| + zona + testigos | 0.79 (0.50-1.23) | 68 % | 24 % |

n = 135. Motivos zona: {'sin_dato': 49, 'ok': 42, 'elegir_zona': 13, 'tope_pedido': 14, 'menor_5': 12, 'conflicto': 5}. Motivos testigos: {None: 34, 'ancla': 81, 'dentro': 9, 'sin_anuncios': 8, 'techo': 3}.

## Por municipio

| municipio | n | motor | + zona | + testigos | fuera motor → zona → testigos |
|---|---|---|---|---|---|
| castellon de la plana | 22 | 0.72 (0.41-1.19) | 0.77 (0.42-1.19) | 0.79 (0.42-1.19) | 73 % → 64 % → 59 % |
| almassora | 15 | 0.79 (0.63-1.38) | 0.83 (0.63-1.57) | 0.83 (0.61-1.57) | 60 % → 67 % → 60 % |
| benicassim | 15 | 1.01 (0.44-1.75) | 0.75 (0.43-1.57) | 0.82 (0.50-1.57) | 73 % → 87 % → 80 % |
| burriana | 15 | 0.76 (0.51-1.45) | 0.68 (0.56-1.59) | 0.82 (0.58-1.75) | 80 % → 80 % → 67 % |
| vila-real | 15 | 0.65 (0.52-0.93) | 0.65 (0.55-1.06) | 0.62 (0.48-0.99) | 73 % → 73 % → 80 % |
| oropesa del mar | 14 | 1.14 (0.50-1.83) | 1.14 (0.48-1.51) | 0.99 (0.46-1.26) | 100 % → 100 % → 79 % |
| onda | 12 | 0.76 (0.55-1.38) | 0.76 (0.55-1.38) | 0.76 (0.55-1.38) | 58 % → 58 % → 58 % |
| nules | 10 | 0.83 (0.52-1.16) | 0.83 (0.52-1.16) | 0.83 (0.52-1.16) | 60 % → 60 % → 60 % |
| el grau de castello | 7 | 0.86 | 0.86 | 0.79 | 43 % → 43 % → 57 % |
| alcora | 1 | 0.78 | 0.78 | 0.78 | 0 % → 0 % → 0 % |
| artana | 1 | 0.60 | 0.60 | 0.60 | 100 % → 100 % → 100 % |
| borriol | 1 | 0.55 | 0.55 | 0.55 | 100 % → 100 % → 100 % |
| madrid | 1 | 1.63 | 1.18 | 1.13 | 100 % → 100 % → 100 % |
| paterna | 1 | 0.71 | 0.94 | 0.80 | 100 % → 0 % → 0 % |
| playa de bellreguard | 1 | 0.61 | 0.61 | 0.61 | 100 % → 100 % → 100 % |
| ribesalbes | 1 | 0.61 | 0.61 | 0.61 | 100 % → 100 % → 100 % |
| san joan de moro | 1 | 0.47 | 0.47 | 0.47 | 100 % → 100 % → 100 % |
| tales | 1 | 2.02 | 2.02 | 2.02 | 100 % → 100 % → 100 % |
| torreblanca | 1 | 0.47 | 0.47 | 0.47 | 100 % → 100 % → 100 % |

## Por municipio y tipo (n ≥ 2)

| municipio | tipo | n | motor | + zona | + testigos | fuera |
|---|---|---|---|---|---|---|
| almassora | adosado | 5 | 0.99 | 1.12 | 0.95 | 40 % → 80 % → 40 % |
| almassora | piso | 8 | 0.76 | 0.80 | 0.75 | 62 % → 50 % → 62 % |
| benicassim | adosado | 3 | 0.44 | 0.44 | 0.51 | 100 % → 100 % → 100 % |
| benicassim | chalet | 2 | 1.23 | 0.70 | 0.79 | 50 % → 50 % → 100 % |
| benicassim | pareado | 2 | 1.28 | 1.26 | 1.03 | 100 % → 100 % → 100 % |
| benicassim | piso | 8 | 0.96 | 0.71 | 0.80 | 62 % → 88 % → 62 % |
| burriana | atico | 2 | 0.68 | 0.64 | 0.69 | 100 % → 100 % → 50 % |
| burriana | chalet | 6 | 0.79 | 0.72 | 0.83 | 67 % → 83 % → 67 % |
| burriana | piso | 6 | 0.73 | 0.71 | 0.74 | 83 % → 67 % → 67 % |
| castellon de la plana | adosado | 2 | 1.09 | 1.23 | 0.95 | 100 % → 50 % → 50 % |
| castellon de la plana | chalet | 4 | 0.41 | 0.43 | 0.43 | 100 % → 100 % → 100 % |
| castellon de la plana | pareado | 2 | 0.88 | 0.88 | 0.73 | 100 % → 100 % → 50 % |
| castellon de la plana | piso | 13 | 0.77 (0.48-1.17) | 0.78 (0.46-1.17) | 0.79 (0.47-1.25) | 62 % → 54 % → 54 % |
| el grau de castello | piso | 6 | 0.80 | 0.80 | 0.80 | 50 % → 50 % → 67 % |
| nules | piso | 9 | 0.84 | 0.84 | 0.84 | 56 % → 56 % → 56 % |
| onda | casa | 2 | 1.14 | 1.14 | 1.14 | 50 % → 50 % → 50 % |
| onda | piso | 8 | 0.72 | 0.72 | 0.72 | 62 % → 62 % → 62 % |
| oropesa del mar | adosado | 2 | 1.48 | 1.16 | 1.08 | 100 % → 100 % → 100 % |
| oropesa del mar | pareado | 2 | 1.18 | 1.20 | 0.94 | 100 % → 100 % → 0 % |
| oropesa del mar | piso | 10 | 1.14 (0.48-1.68) | 1.09 (0.47-1.68) | 0.98 (0.46-1.28) | 100 % → 100 % → 90 % |
| vila-real | piso | 13 | 0.65 (0.51-0.96) | 0.65 (0.55-1.11) | 0.63 (0.52-1.05) | 85 % → 77 % → 77 % |

## Pisos frente a casas

| tipo | n | motor | + zona | + testigos | fuera |
|---|---|---|---|---|---|
| pisos/áticos | 91 | 0.75 (0.49-1.16) | 0.75 (0.50-1.16) | 0.77 (0.49-1.16) | 71 % → 68 % → 66 % |
| casas | 44 | 0.85 (0.44-1.59) | 0.91 (0.44-1.50) | 0.85 (0.48-1.50) | 75 % → 82 % → 73 % |

## Cuando los testigos actúan (ancla/techo, n = 84)

- Acercan al centro del margen (0,875) en 49 de 84 casos (58 %).
- Pasan de fuera a dentro del margen: 13; de dentro a fuera: 7.
- Nº de anuncios por búsqueda: mediana 7.0, excluidos por ser el propio anuncio: 105 en total.
- Tiempo: mediana 71 s por anuncio (motor + zona×2 + testigos, sin caché en la primera búsqueda).

## Peores casos tras testigos (|log ratio| mayor)

| id | municipio | tipo | m² | pedido | motor | zona | testigos | motivo zona | motivo testigos | n |
|---|---|---|---|---|---|---|---|---|---|---|
| 126 | el grau de castello | piso | 39 | 165000 | 0.42 | 0.42 | 0.22 | conflicto | techo | 2 |
| 155 | el grau de castello | piso | 142 | 595000 | 0.41 | 0.41 | 0.35 | sin_dato | ancla | 9 |
| 58 | castellon de la plana | chalet | 277 | 539000 | 0.41 | 0.41 | 0.41 | elegir_zona | dentro | 3 |
| 101 | castellon de la plana | chalet | 277 | 539000 | 0.41 | 0.41 | 0.41 | elegir_zona | dentro | 3 |
| 235 | burriana | chalet | 312 | 250000 | 1.51 | 1.87 | 2.34 | ok | ancla | 9 |
| 231 | castellon de la plana | piso | 41 | 135000 | 0.47 | 0.45 | 0.45 | tope_pedido | ancla | 6 |
| 132 | vila-real | adosado | 80 | 125000 | 0.85 | 0.85 | 0.45 | menor_5 | techo | 2 |
| 287 | castellon de la plana | chalet | 300 | 645000 | 0.45 | 0.45 | 0.45 | sin_dato | sin_anuncios | 0 |
| 260 | oropesa del mar | piso | 80 | 290000 | 0.47 | 0.47 | 0.46 | sin_dato | ancla | 8 |
| 288 | oropesa del mar | piso | 80 | 290000 | 0.64 | 0.50 | 0.47 | ok | ancla | 8 |
| 177 | san joan de moro | atico | 94 | 220000 | 0.47 | 0.47 | 0.47 | sin_dato | None | None |
| 244 | torreblanca | piso | 90 | 315000 | 0.47 | 0.47 | 0.47 | sin_dato | None | None |
| 170 | benicassim | piso | 80 | 375000 | 0.88 | 0.51 | 0.48 | tope_pedido | ancla | 10 |
| 143 | castellon de la plana | piso | 129 | 350000 | 0.49 | 0.49 | 0.49 | elegir_zona | None | None |
| 262 | tales | adosado | 137 | 65000 | 2.02 | 2.02 | 2.02 | sin_dato | None | None |

## Casos con tope «firmado < pedido» (n = 14)

| id | municipio | tipo | pedido | motor | zona | testigos | testigos n |
|---|---|---|---|---|---|---|---|
| 87 | benicassim | chalet | 795000 | 0.80 | 0.43 | 0.51 | 7 |
| 78 | benicassim | pareado | 570000 | 1.28 | 1.26 | 1.03 | 4 |
| 94 | benicassim | pareado | 570000 | 1.28 | 1.26 | 1.03 | 4 |
| 62 | benicassim | chalet | 449000 | 1.66 | 0.97 | 1.08 | 7 |
| 225 | benicassim | piso | 200000 | 1.01 | 0.75 | 0.82 | 8 |
| 170 | benicassim | piso | 375000 | 0.88 | 0.51 | 0.48 | 10 |
| 295 | benicassim | piso | 375000 | 1.01 | 0.58 | 0.56 | 9 |
| 261 | benicassim | piso | 290000 | 0.92 | 0.68 | 0.78 | 5 |
| 228 | castellon de la plana | piso | 242000 | 0.67 | 0.58 | 0.54 | 8 |
| 121 | castellon de la plana | piso | 155000 | 0.61 | 0.63 | 0.79 | 9 |
| 231 | castellon de la plana | piso | 135000 | 0.47 | 0.45 | 0.45 | 6 |
| 15 | madrid | piso | 450000 | 1.63 | 1.18 | 1.13 | 9 |
| 207 | oropesa del mar | piso | 135000 | 1.38 | 1.21 | 1.05 | 8 |
| 77 | oropesa del mar | piso | 155000 | 1.19 | 1.04 | 1.03 | 8 |
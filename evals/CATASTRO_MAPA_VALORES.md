# Mapa de valores de referencia de Catastro como fuente de micro-zona (2026-11-07)

Endpoint público (sin identificación, GET, ~0,5 s, ~400 KB por municipio):

    https://www1.sedecatastro.gob.es/Cartografia/SECDameGeoJSON.aspx?del=0&mun=0&huso=3857&x=<X 3857>&y=<Y 3857>&suelo=N&tipo_mapa=vivienda&anyoZV=2026

Devuelve todos los ámbitos del municipio que contiene el punto (polígonos WGS84). Por ámbito: `cod_zona`, `num_inmuebles_uso_v`, `Ptipo1` (tipología colectiva / unifamiliar aislada-pareada / hilera, superficie, antigüedad, categoría, conservación, `val_tipo_m2`, `val_estandar_m2`). `ejercicio` = año del dato (mapa 2026 → dato 2025). Los códigos de zona cambian de un año a otro.

## Qué mide
Módulo de valor medio del producto representativo (piso tipo de 80-112 m², 32-50 años, calidad media) de cada ámbito, derivado de compraventas ante notario. **No es nivel de mercado**: mediana módulo×m² / precio pedido = 0,47 en los anuncios captados. Vale como gradiente intra-municipio.

## Prueba (119 anuncios del backtest local con ámbito; sin datos en este repo, están en el workspace privado)
Gradiente = módulo de la zona / media ponderada por nº de viviendas de las zonas de la misma clase del municipio; elasticidad 0,5; tope ±30 %; solo cuando la clase del anuncio coincide con la del producto de la zona (30/119 no coinciden).

| | ponencia actual (`zona_valor` WMS) | mapa de valores |
|---|---|---|
| cobertura | 46 / 119 con gradiente | 119 / 140 con ámbito |
| corr(log pedido/Notariado, log gradiente), casos comunes n=37 | 0,34 | 0,55 |
| corr en todos los de misma clase (n=85) | — | 0,43 |
| % fuera de [0,75-1,0] | 74 % | 69 % |
| MAD del log ratio | 0,256 | 0,264 |

Conclusión: señal de ubicación real y con cobertura completa, mejor que la ponencia donde ambas existen, pero con precios pedidos no se puede demostrar mejora de precisión (misma situación que los testigos de oferta, ver `CRITICO_TESTIGOS.md`). Candidato a sustituir la fuente de `mcp_servers/zona_valor/server.py`; antes: golden set del motor, backtest y crítico, idealmente con cierres reales.

Limitaciones vistas: el producto de la zona suele ser colectiva aunque haya chalets (clase distinta → sin gradiente); dato con un año de retraso; en playa el punto puede caer sin ámbito; el servicio devolvió HTML en vez de JSON en 3 peticiones seguidas una vez (reintentar).

## Implementación (2026-11-07, tarde) — ⚠️ NO desplegada
`mcp_servers/zona_valor/server.py::mapa_valores_gradient` + cascada en `valuation_api/engine.py` (6a): primero el mapa, si no ponencia; `ZONA_VALOR_MAPA=0` lo apaga. Tests `valuation_api/test_mapa_valores.py` (10, sin red). Golden: 12 valoraciones reales con el interruptor apagado = idénticas (solo se añade `zone_source`).

Backtest con el motor real (132 pares limpios, `compara_mapa.py` en el workspace privado): fuera de [0,75-1,0] 73 → 68 %, MAD log 0,251 → 0,240, acerca al centro 49 / aleja 31, fuera→dentro 9 / dentro→fuera 2; gradiente aplicado en 92 de 106 casos con calle (81 mapa + 11 ponencia) frente a 49. Ningún municipio empeora en % fuera; la MAD sube en Castellón y Benicàssim por 3-4 casos sueltos (duplicados y unifamiliares con base alta), no por patrón.

Crítico (`CRITICO_MAPA_VALORES.md`): ACEPTAR CON CAMBIOS. Hechos antes del commit: caché por bbox + respaldo de anillos antes de descargar y caché negativa de puntos sin ámbito (1 h); huecos de polígono respetados; timeout 25 → 10 s; HTML en ambos años = fuente caída; tope ±15 % en municipios con > 100 ámbitos (Madrid/Valencia, sin backtest); Ptipo2 ponderado con su `num_inmueble`. Pendiente: textos de la app y de `valuation_copy.py` («zona de valor del Catastro» → «ámbito del mapa de valores»); recalibrar elasticidad (OLS 1,67 sugiere 0,7-0,8) solo con cierres reales; backtest con Valencia/Madrid.

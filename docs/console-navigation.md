# Manual de navegación — Consola Google Cloud (Decomind Agent)

> Guía práctica: en cada pantalla, **qué ves** y **qué cosas puedes hacer**.
> Todas las URLs ya llevan `?project=decomind-agent-challenge`.
>
> Truco: arriba a la izquierda, el **selector de proyecto** debe decir
> "Decomind Agent Challenge". La **barra de búsqueda** (arriba, `/`) te lleva a
> cualquier servicio escribiendo su nombre ("Cloud Run", "Logging"…).

---

## 1. Cloud Run — el panel que más usarás

🔗 `https://console.cloud.google.com/run?project=decomind-agent-challenge`

**Qué ves:** lista de los 7 servicios (6 MCP + `decomind-agent-ui`), cada uno con
su estado (✓ verde), región, URL y último despliegue.

**Cosas que puedes hacer (clic en un servicio, p. ej. `mcp-notariado`):**
- **Pestaña "Métricas":** gráficas de peticiones/seg, latencia, % de errores,
  uso de CPU/memoria. → Para ver si algo va lento o falla.
- **Pestaña "Revisiones":** cada despliegue crea una revisión. Ves el historial,
  qué % de tráfico tiene cada una, y puedes **volver a una anterior** (rollback)
  si un deploy rompe algo.
- **Pestaña "Registros" (Logs):** los logs en vivo de ese servicio. → Para
  depurar (aquí vimos los 403, los errores de Catastro, etc.).
- **Pestaña "YAML":** la config completa del servicio (env vars, memoria, SA).
- **Botón "Editar e implementar nueva revisión":** cambiar memoria, CPU,
  variables de entorno, etc. sin redeploy desde cero.
- **Pestaña "Seguridad/Permisos":** quién puede invocarlo (verás `allUsers` en
  el frontend, y las service accounts en los MCP privados).
- **La URL** (arriba): clic para abrir el servicio en el navegador.

**Para qué te sirve:** monitorizar, depurar (logs), hacer rollback, ver qué
identidad puede llamar a cada servicio.

---

## 2. Vertex AI — Agent Engine (tu agente desplegado)

🔗 `https://console.cloud.google.com/vertex-ai/agents/agent-engines?project=decomind-agent-challenge`

**Qué ves:** tu agente "Decomind Dossier Agent" con su ID
(`8355329596958179328`).

**Cosas que puedes hacer (clic en el agente):**
- **Playground:** un chat para **probar el agente en vivo** (escribe una
  dirección → ves los tool calls y el resultado). Ideal para demos.
- Ver la configuración del Reasoning Engine y su estado.
- Copiar el resource name para invocarlo por API.

**Para qué te sirve:** demostrar "agente desplegado en la plataforma de Google"
(Gemini Enterprise) y probarlo sin la web.

---

## 3. Vertex AI — Model Garden (los modelos)

🔗 `https://console.cloud.google.com/vertex-ai/model-garden?project=decomind-agent-challenge`

**Qué ves:** catálogo de modelos (Gemini 3.5 Flash, 3.1 Pro, Nano Banana…).

**Cosas que puedes hacer:**
- Ver qué modelos hay disponibles y su descripción (así descubriste 3.5 Flash).
- Abrir un modelo y probarlo en un playground rápido.
- Ver detalles de versión/región.

**Para qué te sirve:** elegir/cambiar el modelo del agente (`AGENT_MODEL`).

---

## 4. Cloud Storage — los PDFs generados

🔗 `https://console.cloud.google.com/storage/browser?project=decomind-agent-challenge`

**Qué ves:** los buckets: `decomind-agent-dossiers` (PDFs) y
`decomind-agent-staging` (artefactos de deploy).

**Cosas que puedes hacer (entra en `decomind-agent-dossiers`):**
- Ver todos los **PDFs generados** (`dossier_*.pdf`).
- Clic en uno → descargarlo, ver su URL pública, ver metadatos.
- Borrar PDFs antiguos.
- **Pestaña "Permisos":** ves `allUsers: objectViewer` (lo que hace que las
  URLs públicas funcionen).

**Para qué te sirve:** comprobar que los dossiers se guardan, recuperar uno,
gestionar almacenamiento.

---

## 5. Cloud Build — historial de despliegues

🔗 `https://console.cloud.google.com/cloud-build/builds?project=decomind-agent-challenge`

**Qué ves:** lista de builds (uno por cada `gcloud run deploy`), con verde (OK)
o rojo (falló) y duración.

**Cosas que puedes hacer (clic en un build):**
- Ver los **logs de construcción** paso a paso (útil si un deploy falla:
  aquí ves el error de `pip install`, del Dockerfile, etc.).
- Ver qué imagen se construyó y a qué servicio fue.
- Re-ejecutar un build.

**Para qué te sirve:** depurar despliegues que fallan.

---

## 6. IAM & Admin — identidades y permisos

**Service Accounts (cuentas robot):**
🔗 `https://console.cloud.google.com/iam-admin/serviceaccounts?project=decomind-agent-challenge`
- Ves `decomind-agent-dev` (la identidad del agente y los MCP).
- Clic → ver sus roles, sus permisos.

**IAM (quién puede qué en el proyecto):**
🔗 `https://console.cloud.google.com/iam-admin/iam?project=decomind-agent-challenge`
- Ves todas las cuentas (tu usuario, las service accounts) y sus roles.
- Puedes **añadir/quitar roles** (botón lápiz).

**Organization Policies (las políticas heredadas):**
🔗 `https://console.cloud.google.com/iam-admin/orgpolicies?project=decomind-agent-challenge`
- Aquí está "Domain restricted sharing" que **override-aste** para permitir
  `allUsers` (la URL pública). Puedes ver/revertir ese override.

**Para qué te sirve:** controlar quién accede a qué; gestionar el acceso público.

---

## 7. Logging — el buscador de logs de todo

🔗 `https://console.cloud.google.com/logs/query?project=decomind-agent-challenge`

**Qué ves:** un buscador de todos los logs del proyecto.

**Cosas que puedes hacer:**
- Filtrar por servicio: en el buscador escribe
  `resource.labels.service_name="mcp-notariado"` y ves solo sus logs.
- Filtrar por severidad (ERROR, WARNING) para encontrar problemas rápido.
- Ver logs del Agent Engine (Reasoning Engine) — aquí vimos el
  `UNEXPECTED_TOOL_CALL`.
- Guardar consultas frecuentes.

**Para qué te sirve:** depuración profunda cuando los logs de un servicio
concreto no bastan.

---

## 8. Trace — rendimiento de las peticiones

🔗 `https://console.cloud.google.com/traces/list?project=decomind-agent-challenge`

**Qué ves:** trazas del agente (Agent Engine corre con `--trace_to_cloud`).

**Cosas que puedes hacer:**
- Abrir una traza → ver el **tiempo de cada paso** (cada tool call, cada llamada
  al modelo) en una línea temporal.
- Identificar qué tool es la más lenta.

**Para qué te sirve:** demostrar observabilidad ("X tool calls en N segundos") y
optimizar. Buen material para el vídeo.

---

## 9. Billing — los créditos del challenge

🔗 `https://console.cloud.google.com/billing?project=decomind-agent-challenge`

**Qué ves:** la cuenta de facturación y los créditos.

**Cosas que puedes hacer:**
- **"Credits":** ver cuánto queda de los $500 del challenge.
- **"Reports":** desglose de gasto por servicio (verás que casi todo es céntimos).
- Configurar alertas de presupuesto.

**Para qué te sirve:** confirmar que no te pasas de los créditos (vas
sobradísimo: céntimos por dossier).

---

## 10. APIs y servicios — qué está habilitado

🔗 `https://console.cloud.google.com/apis/dashboard?project=decomind-agent-challenge`

**Qué ves:** las APIs habilitadas (Vertex AI, Cloud Run, Cloud Build, Storage,
IAM, Org Policy…).

**Cosas que puedes hacer:**
- Ver uso de cada API (peticiones, errores).
- Habilitar APIs nuevas si añades servicios.

---

## Recorrido recomendado (10 min, para que todo encaje)

1. **Cloud Run** → clic en `decomind-agent-ui` → abre su URL (tu demo pública).
2. En el mismo, clic en `mcp-notariado` → pestaña Registros (ve sus logs).
3. **Agent Engine** → tu agente → Playground → escribe una dirección y míralo
   ejecutar.
4. **Cloud Storage** → `decomind-agent-dossiers` → abre un PDF.
5. **Trace** → abre una traza → mira los tiempos por tool.
6. **Billing → Credits** → comprueba los créditos restantes.

Con eso has "tocado" cada pieza del sistema en la consola.

---

## Tabla rápida: "quiero hacer X → voy a Y"

| Quiero… | Voy a… |
|---|---|
| Probar el agente sin la web | Agent Engine → Playground |
| Ver por qué falló algo | Cloud Run → servicio → Registros (o Logging) |
| Ver un dossier generado | Cloud Storage → decomind-agent-dossiers |
| Volver a una versión anterior | Cloud Run → servicio → Revisiones → rollback |
| Cambiar una variable de entorno | Cloud Run → servicio → Editar nueva revisión |
| Ver cuánto gasto | Billing → Reports / Credits |
| Saber quién puede llamar un MCP | Cloud Run → servicio → Seguridad/Permisos |
| Ver si un deploy se construyó bien | Cloud Build → builds |
| Cambiar de modelo Gemini | Model Garden (ver) + AGENT_MODEL (cambiar) |
| Gestionar acceso público | IAM → Organization Policies / servicio → Permisos |

---

_Regenerar PDF: `python -m scripts.md_to_pdf docs/console-navigation.md`_

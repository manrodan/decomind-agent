# Reglas de aislamiento

> Copia operativa para este repo. La fuente canónica vive en `~/.claude/projects/C--ProyectosVS-Propelhome/memory/project_google_agents_challenge.md`.

**Mantra:** *"Si rompe lo que factura, NO entra en el plan del challenge."*

## Cero contacto con producción

| Zona producción | Estado durante el challenge |
|---|---|
| `propelhome-backend` (Flask) | ❌ NO se toca |
| `decomind-partner-api` Function App `fa-decomind-partner` | ❌ NO se toca |
| `propelhome-frontend` ramas `main`, `web-main`, `app-main` | ❌ NO se toca |
| BBDD `decomind-pricing-db` | ❌ NO se escribe (lecturas read-only para evals si hace falta) |
| Storage accounts `partner` y `propelhome-uploads` | ❌ NO se escribe |
| Stripe, APIM, dominios `decomind.es` / `app.decomind.es` | ❌ NO se toca |

## Lo que SÍ se puede

- Leer (read-only) código y docs de los repos de producción para inspirarse.
- Copiar lógica de `shared/deep_research.py`, `pdf_dossier.py`, `labor_costs.py`, `roi_provider.py`, `geocoding.py` al sandbox y modificar la copia.
- Exportar dataset anonimizado de inmuebles para evals.

## Check operativo en cada PR / commit

Antes de mergear cualquier cosa en este repo, confirma:

```powershell
cd C:\ProyectosVS\decomind-partner-api && git status
cd C:\ProyectosVS\Propelhome && git status
```

Ambos deben estar **limpios**. Si tu cambio del challenge te empujó a editar algo de producción, ese cambio NO entra en este sprint.

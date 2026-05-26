"""
Día 7 — Smoke test multi-dirección.

Lanza el agente Decomind contra 6 casos curados que cubren distintos perfiles
de mercado (premium, popular, MITMA municipal vs solo provincial, etc.). Genera
un PDF por caso en outputs/ y al final imprime un mapeo caso → archivo para
que sea fácil revisar cuál es cuál.

Uso:
    python -m scripts.demo_set
    python -m scripts.demo_set --only 1,3    # solo los casos 1 y 3
    python -m scripts.demo_set --list        # solo lista los casos
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from google.genai import types

from agent.main import root_agent

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "outputs"

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "?")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west1")
MODEL = os.environ.get("AGENT_MODEL", "gemini-2.5-flash")


# ── Casos curados ─────────────────────────────────────────────────────────
# Cada caso tiene un perfil de mercado distinto. Si tu design partner trabaja
# en una zona concreta, sustituye el caso 1 o añade uno nuevo al final.

CASES: list[dict] = [
    {
        "label": "madrid-centro-reformar",
        "comment": "Madrid Centro, a reformar — caso baseline (MITMA municipal + multiplicador Centro)",
        "prompt": (
            "Prepara dossier completo para:\n"
            "- Calle Mayor 5, Madrid, CP 28013\n"
            "- 95 m², a_reformar, año 1965\n"
            "- Estancias: salón 24, cocina 11, baño 5, dormitorio principal 16, "
            "dormitorio secundario 12, pasillo 7\n"
            "- Tier: standard\n"
            "Genera el PDF al final."
        ),
    },
    {
        "label": "madrid-salamanca-premium",
        "comment": "Madrid Salamanca, en buen estado — premium, ROI flojo esperado",
        "prompt": (
            "Prepara dossier completo para:\n"
            "- Calle Velázquez 50, Madrid, CP 28001\n"
            "- 140 m², buen_estado, año 2005\n"
            "- Estancias: salón 30, cocina 14, baño 6, baño 5, "
            "dormitorio principal 18, dormitorio secundario 14, "
            "dormitorio secundario 12, pasillo 8\n"
            "- Tier: premium\n"
            "Genera el PDF al final."
        ),
    },
    {
        "label": "madrid-vallecas-reformar",
        "comment": "Puente de Vallecas, a reformar — popular, ROI alto esperado",
        "prompt": (
            "Prepara dossier completo para:\n"
            "- Avenida de la Albufera 200, Madrid, CP 28038\n"
            "- 72 m², a_reformar, año 1970\n"
            "- Estancias: salón 18, cocina 8, baño 4, dormitorio principal 12, "
            "dormitorio secundario 10, pasillo 5\n"
            "- Tier: economy\n"
            "Genera el PDF al final."
        ),
    },
    {
        "label": "bilbao-centro",
        "comment": "Bilbao centro — MITMA municipal sin multiplicador distrito",
        "prompt": (
            "Prepara dossier completo para:\n"
            "- Calle Iparraguirre 10, Bilbao, CP 48011\n"
            "- 85 m², a_reformar, año 1955\n"
            "- Estancias: salón 22, cocina 10, baño 5, dormitorio principal 14, "
            "dormitorio secundario 11, pasillo 6\n"
            "- Tier: standard\n"
            "Genera el PDF al final."
        ),
    },
    {
        "label": "valencia-ruzafa",
        "comment": "Valencia (Ruzafa) — MITMA municipal, TAM secundario",
        "prompt": (
            "Prepara dossier completo para:\n"
            "- Carrer de Cuba 25, Valencia, CP 46006\n"
            "- 78 m², a_reformar, año 1972\n"
            "- Estancias: salón 20, cocina 9, baño 5, dormitorio principal 13, "
            "dormitorio secundario 11, pasillo 5\n"
            "- Tier: standard\n"
            "Genera el PDF al final."
        ),
    },
    {
        "label": "marbella-buen-estado",
        "comment": "Marbella (Málaga costa) — MITMA municipal alto",
        "prompt": (
            "Prepara dossier completo para:\n"
            "- Avenida Ricardo Soriano 30, Marbella, CP 29602\n"
            "- 110 m², buen_estado, año 2000\n"
            "- Estancias: salón 28, cocina 12, baño 6, baño 5, "
            "dormitorio principal 16, dormitorio secundario 13, pasillo 7\n"
            "- Tier: standard\n"
            "Genera el PDF al final."
        ),
    },
    {
        "label": "benicassim-real",
        "comment": "Benicassim (Castellón) — pueblo costero, MITMA puede no cubrirlo → fallback provincia",
        "prompt": (
            "Prepara dossier completo para este inmueble real:\n"
            "- Calle Bayer 14, Benicàssim, CP 12560 (provincia Castellón)\n"
            "- 84 m², a_reformar, año 1957\n"
            "- Características: 2 dormitorios, 1 baño, sin ascensor, "
            "calidad de construcción normal, certificación energética baja "
            "(<303,7 kWh/m²/año, etiqueta E/F).\n"
            "- Distribución estimada: salón 22, cocina 9, baño 4, "
            "dormitorio principal 15, dormitorio secundario 12, pasillo 6\n"
            "- Tier de reforma: standard\n"
            "\n"
            "Importante: la baja eficiencia energética y la falta de ascensor "
            "deben mencionarse en tu veredicto final como factores que afectan "
            "a la liquidez del inmueble en el mercado.\n"
            "Genera el PDF al final."
        ),
    },
]


# ── Runner ────────────────────────────────────────────────────────────────

async def run_one(case: dict, idx: int, total: int) -> dict:
    """Lanza el agente para un caso y devuelve métricas + último PDF generado."""
    print(f"\n{'='*70}")
    print(f"  [{idx}/{total}] {case['label']}")
    print(f"  {case['comment']}")
    print(f"{'='*70}\n")

    runner = InMemoryRunner(agent=root_agent, app_name="decomind-agent-demoset")
    session = await runner.session_service.create_session(
        app_name="decomind-agent-demoset", user_id=f"demo-{case['label']}"
    )

    content = types.Content(
        role="user", parts=[types.Part.from_text(text=case["prompt"])]
    )

    pdfs_before = {p.name for p in OUTPUT_DIR.glob("dossier_*.pdf")} if OUTPUT_DIR.exists() else set()
    t0 = time.time()
    tool_calls: list[str] = []
    final_text_chunks: list[str] = []

    async for event in runner.run_async(
        user_id=f"demo-{case['label']}",
        session_id=session.id,
        new_message=content,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.function_call:
                    tool_calls.append(part.function_call.name)
                    print(f"  → {part.function_call.name}")
                elif part.text:
                    final_text_chunks.append(part.text)

    elapsed = time.time() - t0
    pdfs_after = {p.name for p in OUTPUT_DIR.glob("dossier_*.pdf")} if OUTPUT_DIR.exists() else set()
    new_pdfs = sorted(pdfs_after - pdfs_before)
    new_pdf = new_pdfs[-1] if new_pdfs else None

    print(f"\n  ⏱  {elapsed:.1f}s   tools: {len(tool_calls)}   pdf: {new_pdf or '— (no se generó)'}")

    return {
        "label": case["label"],
        "comment": case["comment"],
        "elapsed_s": round(elapsed, 1),
        "tool_calls": tool_calls,
        "pdf": new_pdf,
        "text_preview": ("".join(final_text_chunks))[:300],
    }


async def run_all(selection: list[int] | None) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    chosen = [(i, c) for i, c in enumerate(CASES, start=1) if not selection or i in selection]
    if not chosen:
        print("No hay casos seleccionados.")
        return

    print(f"\nEjecutando {len(chosen)}/{len(CASES)} casos contra {MODEL} @ {PROJECT}\n")
    results: list[dict] = []
    for idx, case in chosen:
        try:
            r = await run_one(case, idx, len(chosen))
        except Exception as exc:
            print(f"  ❌ ERROR: {exc}")
            r = {"label": case["label"], "error": str(exc), "pdf": None}
        results.append(r)

    # Resumen
    print("\n" + "=" * 70)
    print("  RESUMEN")
    print("=" * 70)
    for r in results:
        status = "✅" if r.get("pdf") else "❌"
        elapsed = f"{r.get('elapsed_s', 0):>5.1f}s" if r.get("elapsed_s") else "  err"
        pdf = r.get("pdf") or r.get("error", "—")
        print(f"  {status} {elapsed}  {r['label']:35s}  {pdf}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Día 7 — smoke test multi-dirección")
    parser.add_argument("--only", help="lista de índices 1-based separados por coma, ej. '1,3'")
    parser.add_argument("--list", action="store_true", help="solo listar casos y salir")
    args = parser.parse_args()

    if args.list:
        for i, c in enumerate(CASES, start=1):
            print(f"  [{i}] {c['label']:35s}  {c['comment']}")
        return

    selection: list[int] | None = None
    if args.only:
        selection = [int(x) for x in args.only.split(",") if x.strip().isdigit()]

    asyncio.run(run_all(selection))


if __name__ == "__main__":
    main()

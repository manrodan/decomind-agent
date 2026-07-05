"""Construye data/seccion_signal.json — señal de mercado por sección censal.

Combina DOS fuentes oficiales para que el motor de valoración ajuste la
micro-ubicación dentro de un municipio:

1) SERPAVI (MIVAU/MITMA) — Sistema Estatal de Referencia del Precio del
   Alquiler de Vivienda. XLSX oficial con la serie 2011-2024 por sección
   censal. Se usa la MEDIANA del alquiler mensual €/m² de VIVIENDA
   COLECTIVA (columna ALQM2_LV_M_VC_AA), tomando el año más reciente
   disponible por sección (2024 → 2023 → 2022). Las secciones sin dato
   son las suprimidas por secreto estadístico (pocos testigos): el techo
   real de cobertura de la fuente es ~26.5k de las 36.3k secciones.

2) Atlas de Distribución de Renta de los Hogares (INE, ADRH) — renta neta
   media POR HOGAR por sección censal. Vía CSVs preparados del repo
   github.com/pablogguz/ineAtlas.data (fichero income a nivel tract).
   Se toma el último año con dato por sección (2023 → hacia atrás).

Salida (contrato con el motor):
{
  "meta": {"serpavi_edition": "...", "adrh_year": "...", "built_at": "..."},
  "secciones": {"<CUSEC 10 díg>": [alquiler_eur_m2_mes | null, renta_hogar_eur | null]},
  "municipios": {"<CUMUN 5 díg>": [mediana alquiler secciones, mediana renta secciones]}
}

Re-ejecutable: cachea las descargas en data/raw/ (gitignored); bórralas o
usa --force para re-descargar. Requiere: requests, openpyxl (en .venv).

Nota de vintages: SERPAVI usa el seccionado del Censo 2011 y el ADRH el
seccionado vigente de cada año (~2023). La inmensa mayoría de CUSEC
coincide; las secciones renumeradas entre censos simplemente aportan solo
una de las dos señales (la otra queda null).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import statistics
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
OUT_PATH = REPO_ROOT / "data" / "seccion_signal.json"

SERPAVI_URL = (
    "https://cdn.mivau.gob.es/portal-web-mivau/vivienda/serpavi/"
    "2026-03-09_bd_SERPAVI_2011-2024%20-%20DEFINITIVO%20WEB.xlsx"
)
SERPAVI_EDITION = "SERPAVI 2011-2024 (BD definitiva web 2026-03-09), mediana €/m²/mes vivienda colectiva, año 2024 con fallback 2023/2022"
SERPAVI_SHEET = "Secciones censales"
SERPAVI_YEARS = ("24", "23", "22")  # orden de preferencia

ADRH_URL = (
    "https://raw.githubusercontent.com/pablogguz/ineAtlas.data/main/"
    "data/income/income_tract.zip"
)
ADRH_EDITION = "INE ADRH vía ineAtlas.data (income_tract), renta neta media por hogar, último año disponible por sección (2023)"

UA = {"User-Agent": "Mozilla/5.0 (decomind-agent dataset builder)"}


def download(url: str, dest: Path, force: bool = False) -> Path:
    if dest.exists() and dest.stat().st_size > 0 and not force:
        print(f"[cache] {dest.name} ({dest.stat().st_size:,} bytes)")
        return dest
    print(f"[download] {url}")
    resp = requests.get(url, headers=UA, timeout=300)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    print(f"[saved] {dest.name} ({len(resp.content):,} bytes)")
    return dest


def parse_serpavi(path: Path) -> dict[str, float]:
    """CUSEC (10 dígitos) -> mediana alquiler €/m²/mes vivienda colectiva."""
    import openpyxl  # import tardío: carga lenta

    print(f"[parse] SERPAVI {path.name} (hoja '{SERPAVI_SHEET}')...")
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb[SERPAVI_SHEET]
    rows = ws.iter_rows(values_only=True)
    header = next(rows)
    idx = {h: i for i, h in enumerate(header)}
    cusec_i = idx["CUSEC"]
    year_cols = [(y, idx[f"ALQM2_LV_M_VC_{y}"]) for y in SERPAVI_YEARS]

    out: dict[str, float] = {}
    n_rows = 0
    for row in rows:
        n_rows += 1
        cusec = row[cusec_i]
        if cusec is None:
            continue
        cusec = str(cusec).strip().zfill(10)
        if len(cusec) != 10 or not cusec.isdigit():
            continue
        for _year, col in year_cols:
            val = row[col]
            if val is None:
                continue
            if isinstance(val, str):
                # celdas con texto: vacías o con decimal de coma
                val = val.strip().replace(",", ".")
                if not val:
                    continue
                try:
                    val = float(val)
                except ValueError:
                    continue
            out[cusec] = float(val)
            break
    wb.close()
    print(f"[parse] SERPAVI: {n_rows:,} secciones en fichero, {len(out):,} con mediana de alquiler VC")
    return out


def parse_adrh(path: Path) -> dict[str, int]:
    """CUSEC (10 dígitos) -> renta neta media por hogar (€, último año con dato)."""
    print(f"[parse] ADRH {path.name}...")
    best: dict[str, tuple[int, int]] = {}  # cusec -> (year, income)
    with zipfile.ZipFile(path) as zf:
        members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
        if len(members) != 1:
            raise RuntimeError(f"Esperaba 1 CSV dentro del zip, hay {members}")
        with zf.open(members[0]) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            for row in reader:
                v = (row.get("net_income_hh") or "").strip()
                if v in ("", "NA", "NaN"):
                    continue
                cusec = row["tract_code"].strip().zfill(10)
                if len(cusec) != 10 or not cusec.isdigit():
                    continue
                year = int(row["year"])
                try:
                    income = int(round(float(v)))
                except ValueError:
                    continue
                prev = best.get(cusec)
                if prev is None or year > prev[0]:
                    best[cusec] = (year, income)
    out = {c: inc for c, (_y, inc) in best.items()}
    years = sorted({y for y, _ in best.values()})
    n_old = sum(1 for y, _ in best.values() if y != years[-1])
    print(
        f"[parse] ADRH: {len(out):,} secciones con renta por hogar "
        f"(último año {years[-1]}; {n_old:,} secciones con fallback a años previos, mín. {years[0]})"
    )
    return out


def build(force: bool = False) -> dict:
    meta: dict[str, str | None] = {
        "serpavi_edition": None,
        "adrh_year": None,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    alquiler: dict[str, float] = {}
    try:
        serpavi_file = download(SERPAVI_URL, RAW_DIR / "serpavi_2011_2024.xlsx", force)
        alquiler = parse_serpavi(serpavi_file)
        meta["serpavi_edition"] = SERPAVI_EDITION
    except Exception as exc:  # noqa: BLE001 — una fuente caída no debe tirar la otra
        meta["serpavi_edition"] = None
        meta["serpavi_error"] = f"{SERPAVI_URL} -> {type(exc).__name__}: {exc}"
        print(f"[WARN] SERPAVI no disponible: {meta['serpavi_error']}", file=sys.stderr)

    renta: dict[str, int] = {}
    try:
        adrh_file = download(ADRH_URL, RAW_DIR / "adrh_income_tract.zip", force)
        renta = parse_adrh(adrh_file)
        meta["adrh_year"] = "2023 (último año disponible por sección; fallback a años previos donde 2023 está suprimido)"
        meta["adrh_edition"] = ADRH_EDITION
    except Exception as exc:  # noqa: BLE001
        meta["adrh_year"] = None
        meta["adrh_error"] = f"{ADRH_URL} -> {type(exc).__name__}: {exc}"
        print(f"[WARN] ADRH no disponible: {meta['adrh_error']}", file=sys.stderr)

    if not alquiler and not renta:
        raise SystemExit("Ninguna fuente disponible; no se genera el dataset.")

    secciones: dict[str, list] = {}
    for cusec in sorted(set(alquiler) | set(renta)):
        alq = alquiler.get(cusec)
        ren = renta.get(cusec)
        secciones[cusec] = [round(alq, 2) if alq is not None else None, ren]

    # Baseline municipal: mediana de las secciones con dato de cada magnitud.
    by_mun_alq: dict[str, list[float]] = {}
    by_mun_ren: dict[str, list[int]] = {}
    for cusec, (alq, ren) in secciones.items():
        cumun = cusec[:5]
        if alq is not None:
            by_mun_alq.setdefault(cumun, []).append(alq)
        if ren is not None:
            by_mun_ren.setdefault(cumun, []).append(ren)
    municipios: dict[str, list] = {}
    for cumun in sorted(set(by_mun_alq) | set(by_mun_ren)):
        alqs = by_mun_alq.get(cumun)
        rens = by_mun_ren.get(cumun)
        municipios[cumun] = [
            round(statistics.median(alqs), 2) if alqs else None,
            int(round(statistics.median(rens))) if rens else None,
        ]

    return {"meta": meta, "secciones": secciones, "municipios": municipios}


def self_check(data: dict) -> None:
    secciones = data["secciones"]
    municipios = data["municipios"]
    n_alq = sum(1 for v in secciones.values() if v[0] is not None)
    n_ren = sum(1 for v in secciones.values() if v[1] is not None)

    print("\n================ SELF-CHECK ================")
    print(f"Secciones totales en dataset : {len(secciones):,}")
    print(f"  con dato de alquiler       : {n_alq:,}  (techo de la fuente ~26.5k por secreto estadístico)")
    print(f"  con dato de renta/hogar    : {n_ren:,}")
    print(f"Municipios con baseline      : {len(municipios):,}")

    def show_mun(cumun: str, nombre: str, distritos: tuple[str, ...] = ()) -> None:
        mun = municipios.get(cumun)
        print(f"\n--- {nombre} (CUMUN {cumun}) ---")
        if mun is None:
            print("  SIN DATOS")
            return
        print(f"  Mediana municipal: alquiler={mun[0]} €/m²/mes · renta hogar={mun[1]} €")
        for cusec in sorted(secciones):
            if cusec.startswith(cumun) and (not distritos or cusec[5:7] in distritos):
                alq, ren = secciones[cusec]
                print(f"    {cusec}: alquiler={alq} · renta={ren}")

    show_mun("12040", "Castellón de la Plana", distritos=("01", "02"))
    show_mun("12028", "Benicàssim")

    # Coherencia Madrid: la sección más cara debe superar claramente su mediana municipal.
    mad = [(c, v) for c, v in secciones.items() if c.startswith("28079") and v[0] is not None]
    if mad and municipios.get("28079"):
        top_c, top_v = max(mad, key=lambda kv: kv[1][0])
        mun_alq, mun_ren = municipios["28079"]
        print(f"\n--- Coherencia Madrid (28079) ---")
        print(f"  Mediana municipal: alquiler={mun_alq} · renta={mun_ren}")
        print(f"  Sección más cara : {top_c}: alquiler={top_v[0]} · renta={top_v[1]}")
        ok_alq = top_v[0] > mun_alq * 1.2
        ok_ren = top_v[1] is not None and mun_ren is not None and top_v[1] > mun_ren
        print(f"  alquiler top > 1.2x mediana municipal: {'OK' if ok_alq else 'FALLO'}")
        print(f"  renta top > mediana municipal        : {'OK' if ok_ren else 'FALLO (o sin dato)'}")
    print("============================================")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="re-descarga las fuentes ignorando la caché de data/raw/")
    args = ap.parse_args()

    data = build(force=args.force)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n[out] {OUT_PATH} ({OUT_PATH.stat().st_size:,} bytes)")
    self_check(data)


if __name__ == "__main__":
    main()

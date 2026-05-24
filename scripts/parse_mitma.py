"""
Parser del XLS "Valor tasado de la vivienda" (MITMA).

Lee la hoja del trimestre más reciente y genera
`mcp_servers/market_research/data_mitma.py` con:

  - MITMA_QUARTER: str (ej. "2025-Q4")
  - MITMA_SOURCE: str (URL + fuente)
  - PROVINCE_PRICE_PER_SQM_MITMA: dict[str, float]   (mediana de municipios)
  - MUNICIPALITY_PRICE_PER_SQM_MITMA: dict[str, float]

Las claves se normalizan a lowercase sin acentos para hacer lookups robustos.

Uso:
    python -m scripts.parse_mitma
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from statistics import median

import pandas as pd

XLS_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "DatosVivienda.xls"
OUT_PATH = (
    Path(__file__).resolve().parent.parent
    / "mcp_servers" / "market_research" / "data_mitma.py"
)


def normalize_key(s: str) -> str:
    """lowercase + sin acentos + espacios colapsados."""
    s = s.strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s


def latest_quarter_sheet(names: list[str]) -> tuple[str, str]:
    """Devuelve (sheet_name, label_humano). label_humano = '2025-Q4'."""
    pat = re.compile(r"^T(\d)A(\d{4})$", re.IGNORECASE)
    scored: list[tuple[int, str, str]] = []
    for n in names:
        m = pat.match(n)
        if not m:
            continue
        q, y = int(m.group(1)), int(m.group(2))
        scored.append((y * 10 + q, n, f"{y}-Q{q}"))
    if not scored:
        last = sorted(names)[-1]
        return last, last
    scored.sort(reverse=True)
    return scored[0][1], scored[0][2]


def parse(xls_path: Path) -> tuple[str, dict[str, float], dict[str, float]]:
    xls = pd.ExcelFile(xls_path)
    sheet, label = latest_quarter_sheet(xls.sheet_names)
    print(f"Trimestre: {label}  (hoja: {sheet!r})")

    df = pd.read_excel(xls_path, sheet_name=sheet, header=None)

    municipalities: dict[str, float] = {}
    province_to_prices: dict[str, list[float]] = {}
    current_province: str | None = None

    for _, row in df.iterrows():
        prov_cell = row.iloc[1] if len(row) > 1 else None
        muni_cell = row.iloc[2] if len(row) > 2 else None
        total_cell = row.iloc[5] if len(row) > 5 else None

        # Actualizar provincia si la celda trae texto válido
        if isinstance(prov_cell, str) and prov_cell.strip():
            candidate = prov_cell.strip()
            # filtrar cabeceras tipo "PROVINCIA" o cosas raras
            if not candidate.isupper() and len(candidate) > 1:
                current_province = candidate

        if not isinstance(muni_cell, str) or not muni_cell.strip():
            continue
        muni = muni_cell.strip()
        # ignorar cabeceras intermedias del tipo "MUNICIPIO", "Total", etc.
        if muni.lower() in {"municipio", "total", "totales", "nan"}:
            continue
        if muni.isupper():
            continue

        # total €/m² debe ser numérico
        try:
            total = float(total_cell)
        except (TypeError, ValueError):
            continue
        if not (200 < total < 20000):  # rango sano de €/m² España
            continue

        muni_key = normalize_key(muni)
        municipalities[muni_key] = round(total, 1)
        if current_province:
            province_to_prices.setdefault(
                normalize_key(current_province), []
            ).append(total)

    provinces: dict[str, float] = {
        prov: round(median(prices), 1) for prov, prices in province_to_prices.items()
    }
    return label, provinces, municipalities


def write_output(label: str, provinces: dict, municipalities: dict) -> None:
    lines: list[str] = [
        '"""',
        "Datos €/m² oficiales del MITMA — Valor tasado de la vivienda.",
        "",
        "GENERADO AUTOMÁTICAMENTE por scripts/parse_mitma.py — no editar a mano.",
        "Re-generar tras descargar un XLS más reciente desde:",
        "  https://www.mitma.gob.es/informacion-para-el-ciudadano/informacion-estadistica/"
        "vivienda-y-actuaciones-urbanas/estadisticas/vivienda-y-suelo",
        "",
        f"Trimestre fuente: {label}",
        f"Municipios cubiertos: {len(municipalities)}",
        f"Provincias cubiertas: {len(provinces)}",
        '"""',
        "from __future__ import annotations",
        "",
        f'MITMA_QUARTER = "{label}"',
        'MITMA_SOURCE = (',
        '    "MITMA — Valor tasado de la vivienda. '
        'Ministerio de Transportes y Movilidad Sostenible (Gobierno de España)."',
        ')',
        "",
        "PROVINCE_PRICE_PER_SQM_MITMA: dict[str, float] = {",
    ]
    for k in sorted(provinces):
        lines.append(f'    "{k}": {provinces[k]},')
    lines += ["}", "", "MUNICIPALITY_PRICE_PER_SQM_MITMA: dict[str, float] = {"]
    for k in sorted(municipalities):
        lines.append(f'    "{k}": {municipalities[k]},')
    lines += ["}", ""]

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nEscrito: {OUT_PATH}")
    print(f"  {len(provinces)} provincias, {len(municipalities)} municipios")


def main() -> None:
    label, provinces, municipalities = parse(XLS_PATH)
    # sanity check
    print("\nMuestras:")
    for name in ["madrid", "barcelona", "bilbao", "valencia", "sevilla",
                 "malaga", "marbella", "san sebastian", "donostia / san sebastian"]:
        if name in municipalities:
            print(f"  {name:40s} = {municipalities[name]} €/m²")
        elif name in provinces:
            print(f"  (prov) {name:34s} = {provinces[name]} €/m²")
    write_output(label, provinces, municipalities)


if __name__ == "__main__":
    main()

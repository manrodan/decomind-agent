"""
Inspector del XLS del MITMA — analiza la hoja más reciente en profundidad.

El XLS tiene una hoja por trimestre (T<q>A<year>). Solo nos interesa la última.

Uso:
    python -m scripts.inspect_mitma
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

XLS_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "DatosVivienda.xls"


def latest_quarter_sheet(names: list[str]) -> str:
    """Devuelve el nombre de la hoja correspondiente al trimestre más reciente.
    Asume formato T<q>A<year>, donde q=1..4. Si no matchea, último alfabético.
    """
    pat = re.compile(r"^T(\d)A(\d{4})$", re.IGNORECASE)
    scored: list[tuple[int, str]] = []
    for n in names:
        m = pat.match(n)
        if not m:
            continue
        q, y = int(m.group(1)), int(m.group(2))
        scored.append((y * 10 + q, n))
    if not scored:
        return sorted(names)[-1]
    scored.sort(reverse=True)
    return scored[0][1]


def main() -> None:
    if not XLS_PATH.exists():
        raise SystemExit(f"No existe: {XLS_PATH}")

    xls = pd.ExcelFile(XLS_PATH)
    print(f"Total hojas: {len(xls.sheet_names)}")
    print(f"Primera: {xls.sheet_names[0]!r}    Última: {xls.sheet_names[-1]!r}\n")

    latest = latest_quarter_sheet(xls.sheet_names)
    print(f"==> Analizando hoja más reciente: {latest!r}\n")

    # leer entera
    df = pd.read_excel(XLS_PATH, sheet_name=latest, header=None)
    print(f"Dimensiones: {df.shape}\n")

    # 1) cabeceras: primeras 15 filas que contengan al menos UNA celda con texto
    def has_text(row):
        return any(isinstance(x, str) and x.strip() for x in row)

    text_rows = df[df.apply(has_text, axis=1)].head(15)
    print("=== Cabeceras (primeras 15 filas con texto) ===\n")
    with pd.option_context(
        "display.max_columns", 20,
        "display.width", 250,
        "display.max_colwidth", 40,
    ):
        print(text_rows.to_string(header=False))
    print()

    # 2) un municipio de Madrid (para sanity check)
    print("\n=== Buscando Madrid municipio ===\n")
    for idx, row in df.iterrows():
        cells = [str(c) for c in row.tolist()]
        if any("Madrid" == c.strip() for c in cells):
            print(f"Fila {idx}:", cells)
            # imprimir 1 fila siguiente (subtotal transacciones)
            if idx + 1 < len(df):
                next_cells = [str(c) for c in df.iloc[idx + 1].tolist()]
                print(f"Fila {idx + 1}:", next_cells)
            break


if __name__ == "__main__":
    main()

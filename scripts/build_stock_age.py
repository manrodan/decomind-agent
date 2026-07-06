"""
build_stock_age.py — año típico de construcción del parque por sección censal.

Fuente: Catastro INSPIRE Buildings (descarga libre por municipio, GML con
dateOfConstruction, uso y nº de viviendas por edificio) + secciones censales
del INE (OGC API Features, GeoJSON). Cada edificio residencial se asigna a su
sección por punto-en-polígono y se calcula el AÑO MEDIANO ponderado por nº de
viviendas. Salida: data/stock_age.json (contrato del motor):

    {"meta": {...},
     "secciones": {"1204006004": 1974, ...},
     "municipios": {"12040": 1976, ...}}

El fichero se MERGEA en cada ejecución (se puede correr provincia a provincia).
El motor lo consume vía mcp_servers/seccion_censal/server.py:stock_age_year()
— en cuanto exista, la antigüedad relativa del hedónico se activa sola.

Uso (desde la raíz del repo, con el venv):
    .venv\\Scripts\\python.exe scripts\\build_stock_age.py --prov 12
    .venv\\Scripts\\python.exe scripts\\build_stock_age.py --prov 12 --mun BENICASIM
    .venv\\Scripts\\python.exe scripts\\build_stock_age.py --all   (toda España, horas)

Requiere: shapely, pyproj (pip install shapely pyproj). Descargas cacheadas en
data/raw/inspire_bu/ (gitignored).
"""
from __future__ import annotations

import argparse
import io
import json
import re
import statistics
import sys
import time
import zipfile
from datetime import date
from pathlib import Path

import httpx
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "stock_age.json"
CACHE_DIR = ROOT / "data" / "raw" / "inspire_bu"

ATOM_PROV = "https://www.catastro.hacienda.gob.es/INSPIRE/buildings/{p}/ES.SDGC.bu.atom_{p}.xml"
INE_ITEMS = ("https://www.ine.es/geoserver/ogc/features/v1/collections/"
             "WMS_INE_SECCIONES_G01:Secciones_2025/items")
HEADERS = {"User-Agent": "decomind-agent-challenge/0.1 (info@decomind.es)"}

# Provincias con catastro estatal (forales 01/20/48/31 NO están en INSPIRE-SDGC).
ALL_PROVS = [f"{i:02d}" for i in range(2, 53) if i not in (20, 31, 48)] + ["02"]
ALL_PROVS = sorted(set(ALL_PROVS) - {"01"})

_ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.S)
_TITLE_RE = re.compile(r"<title>\s*([0-9]{5})-([^<]+?)\s*buildings", re.I)
_HREF_RE = re.compile(r'href="([^"]+\.zip)"')
_BUILDING_RE = re.compile(r"<bu-ext2d:Building\b(.*?)</bu-ext2d:Building>", re.S)
# La fecha real va en bu-core2d:DateOfEvent/end; los edificios sin año traen
# "--01-01" (no arranca con 4 dígitos → no matchea, se descartan solos).
_YEAR_RE = re.compile(r"<bu-core2d:end>(\d{4})")
_USE_RE = re.compile(r"<bu-ext2d:currentUse>([^<]+)</bu-ext2d:currentUse>")
_DWELL_RE = re.compile(r"<bu-ext2d:numberOfDwellings>(\d+)</bu-ext2d:numberOfDwellings>")
_POS_RE = re.compile(r"<gml:posList[^>]*>([\d.\s\-]+)</gml:posList>")
_SRS_RE = re.compile(r'srsName="[^"]*EPSG:[:]*(\d+)"')


def _fetch(url: str, dest: Path) -> bytes:
    if dest.exists():
        return dest.read_bytes()
    # Los href del ATOM del Catastro llevan espacios literales en el path y los
    # nombres bilingües traen padding (3 espacios) que el servidor NO acepta:
    # la ruta real usa UN espacio ("BENICASIM BENICASSIM"). Colapsar y encodear.
    url = re.sub(r"\s+", " ", url).replace(" ", "%20")
    with httpx.Client(timeout=180, headers=HEADERS, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return r.content


def municipality_entries(prov: str) -> list[tuple[str, str, str]]:
    """[(codigo_catastro, nombre, zip_url)] de la provincia."""
    xml = _fetch(ATOM_PROV.format(p=prov), CACHE_DIR / f"atom_{prov}.xml").decode("utf-8", "replace")
    out = []
    for m in _ENTRY_RE.finditer(xml):
        block = m.group(1)
        t = _TITLE_RE.search(block)
        h = _HREF_RE.search(block)
        if t and h:
            out.append((t.group(1), t.group(2).strip(), h.group(1)))
    return out


def parse_buildings(gml: str) -> list[tuple[float, float, int, int]]:
    """[(lon, lat, año, viviendas)] de los edificios RESIDENCIALES del GML."""
    srs = _SRS_RE.search(gml)
    epsg = int(srs.group(1)) if srs else 25830
    tr = (Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
          if epsg != 4326 else None)
    out = []
    for m in _BUILDING_RE.finditer(gml):
        b = m.group(1)
        dw_m = _DWELL_RE.search(b)
        dwellings = int(dw_m.group(1)) if dw_m else 0
        use = _USE_RE.search(b)
        # Residencial: por uso declarado o, si el uso viene nil (habitual en
        # este GML), por tener viviendas. Fuera almacenes/auxiliares (0 viv).
        if use:
            if "residential" not in use.group(1):
                continue
        elif dwellings < 1:
            continue
        y = _YEAR_RE.search(b)
        if not y:
            continue
        year = int(y.group(1))
        if not 1500 < year <= date.today().year:
            continue
        pos = _POS_RE.search(b)
        if not pos:
            continue
        nums = pos.group(1).split()
        if len(nums) < 2:
            continue
        x, y2 = float(nums[0]), float(nums[1])
        lon, lat = tr.transform(x, y2) if tr else (x, y2)
        out.append((lon, lat, year, max(1, dwellings)))
    return out


def secciones_for_bbox(bbox: tuple[float, float, float, float]) -> list[tuple[object, str, str]]:
    """[(polígono shapely, CUSEC, CUMUN)] de las secciones que tocan el bbox."""
    params = {"f": "application/json",
              "bbox": ",".join(f"{v:.6f}" for v in bbox), "limit": 2000}
    with httpx.Client(timeout=120, headers=HEADERS) as c:
        r = c.get(INE_ITEMS, params=params)
        r.raise_for_status()
        feats = r.json().get("features") or []
    out = []
    for f in feats:
        p = f.get("properties") or {}
        if p.get("TIPO") != "SECCIONADO" or not f.get("geometry"):
            continue
        try:
            out.append((shape(f["geometry"]), p["CUSEC"], p["CUMUN"]))
        except Exception:
            continue
    return out


def weighted_median_year(items: list[tuple[int, int]]) -> int | None:
    """Mediana del año ponderada por nº de viviendas. items = [(año, peso)]."""
    if not items:
        return None
    items = sorted(items)
    total = sum(w for _, w in items)
    acc = 0
    for year, w in items:
        acc += w
        if acc * 2 >= total:
            return year
    return items[-1][0]


def process_municipality(code: str, name: str, zip_url: str,
                         secciones_years: dict[str, list], log=print) -> int:
    raw = _fetch(zip_url, CACHE_DIR / f"{code}.zip")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        gml_names = [n for n in z.namelist() if n.endswith(".building.gml")]
        if not gml_names:
            log(f"  {code}-{name}: sin building.gml, salto")
            return 0
        gml = z.read(gml_names[0]).decode("utf-8", "replace")
    buildings = parse_buildings(gml)
    if not buildings:
        log(f"  {code}-{name}: 0 edificios residenciales con año")
        return 0
    lons = [b[0] for b in buildings]
    lats = [b[1] for b in buildings]
    margin = 0.01
    secs = secciones_for_bbox((min(lons) - margin, min(lats) - margin,
                               max(lons) + margin, max(lats) + margin))
    if not secs:
        log(f"  {code}-{name}: el INE no devuelve secciones para su bbox, salto")
        return 0
    tree = STRtree([s[0] for s in secs])
    assigned = 0
    for lon, lat, year, dw in buildings:
        pt = Point(lon, lat)
        for idx in tree.query(pt):
            poly, cusec, cumun = secs[idx]
            if poly.contains(pt):
                secciones_years.setdefault(cusec, []).append((year, dw))
                assigned += 1
                break
    log(f"  {code}-{name}: {len(buildings)} edificios, {assigned} asignados a "
        f"{len({s[1] for s in secs})} secciones")
    return assigned


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prov", action="append", default=[],
                    help="código de provincia (repetible), ej. --prov 12")
    ap.add_argument("--mun", default="",
                    help="filtro por nombre o código de municipio (contiene)")
    ap.add_argument("--all", action="store_true", help="toda España (horas)")
    args = ap.parse_args()

    provs = ALL_PROVS if args.all else args.prov
    if not provs:
        ap.error("indica --prov NN (repetible) o --all")

    # Merge sobre lo ya construido (se puede correr provincia a provincia).
    existing = {"meta": {}, "secciones": {}, "municipios": {}}
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))

    secciones_years: dict[str, list] = {}
    t0 = time.time()
    for prov in provs:
        print(f"\nProvincia {prov}")
        try:
            entries = municipality_entries(prov)
        except Exception as exc:
            print(f"  ATOM de la provincia {prov} falló: {exc}")
            continue
        for code, name, zip_url in entries:
            if args.mun and args.mun.upper() not in f"{code}-{name}".upper():
                continue
            try:
                process_municipality(code, name, zip_url, secciones_years)
            except Exception as exc:
                print(f"  {code}-{name}: ERROR {exc}")

    # Medianas por sección y por municipio (CUMUN = 5 primeros dígitos del CUSEC).
    new_secs = {c: weighted_median_year(items)
                for c, items in secciones_years.items()}
    new_secs = {c: y for c, y in new_secs.items() if y}
    muni_items: dict[str, list] = {}
    for cusec, items in secciones_years.items():
        muni_items.setdefault(cusec[:5], []).extend(items)
    new_munis = {m: weighted_median_year(items) for m, items in muni_items.items()}

    existing["secciones"].update(new_secs)
    existing["municipios"].update({m: y for m, y in new_munis.items() if y})
    existing["meta"] = {
        "source": "Catastro INSPIRE Buildings (dateOfConstruction, residencial, "
                  "ponderado por nº viviendas) + secciones INE OGC API 2025",
        "built_at": date.today().isoformat(),
        "secciones": len(existing["secciones"]),
        "municipios": len(existing["municipios"]),
    }
    OUT_PATH.write_text(json.dumps(existing, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")

    print(f"\nOK -> {OUT_PATH} ({OUT_PATH.stat().st_size / 1e6:.2f} MB, "
          f"{len(existing['secciones'])} secciones, {time.time() - t0:.0f}s)")
    # Self-check del caso de prueba si está en el dataset.
    for probe in ("1204006004", "12040", "12028"):
        v = existing["secciones"].get(probe) or existing["municipios"].get(probe)
        if v:
            print(f"  check {probe}: año mediano {v}")


if __name__ == "__main__":
    main()

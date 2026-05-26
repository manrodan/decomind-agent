"""
MCP server: Dossier PDF — empaqueta el resultado del agente en un PDF.

Una tool:
  - render_dossier_pdf(...) → genera PDF y devuelve {path, pages, size_bytes}

Estructura del PDF (paridad con Dossier V1 de producción, sin renders ni
shopping list — esos quedan como roadmap M2 opcional/add-on):

  1) Portada (branding + datos del inmueble)
  2) Análisis de zona y valoración actual (mejora V2 vs V1)
  3) Propuesta de reforma (presupuesto desglosado por estancia y oficio)
  4) Resumen de inversión + ROI + veredicto del agente

Estilo visual portado de decomind-partner-api/shared/pdf_dossier.py (canvas
con branding, color primary, _eur helper). Coherencia con el producto en
producción.

Output: PDF en outputs/dossier_<timestamp>.pdf (local). En producción Marketplace
post-challenge, este path se sustituirá por upload a GCS bucket + signed URL.
"""

from __future__ import annotations

import io
import logging
import os
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = REPO_ROOT / "outputs"

# Si está definido DOSSIER_BUCKET, el PDF se sube a GCS y se devuelve URL pública.
# Si no, se escribe localmente en OUTPUT_DIR (dev local con stdio).
GCS_BUCKET = os.environ.get("DOSSIER_BUCKET", "").strip()

logger = logging.getLogger("mcp.dossier_pdf")
mcp = FastMCP("dossier-pdf")


def _persist_pdf(pdf_bytes: bytes, filename: str) -> dict[str, Any]:
    """Persiste el PDF y devuelve {url, location_kind, size_bytes, filename}.

    En modo cloud: sube a GCS y devuelve **signed URL V4** (24h). Sin claves
    privadas locales — usa la API IAM signBlob de Google (SA debe tener
    roles/iam.serviceAccountTokenCreator sobre sí misma).

    En dev local (sin DOSSIER_BUCKET): escribe a outputs/ y devuelve file://.
    """
    size = len(pdf_bytes)
    if GCS_BUCKET:
        from datetime import timedelta
        from google.auth import default as auth_default
        from google.auth.transport.requests import Request
        from google.cloud import storage

        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(filename)
        blob.upload_from_string(pdf_bytes, content_type="application/pdf")

        # Signed URL V4. En Cloud Run, default credentials vienen del metadata
        # server (no hay private key local). Hay que firmar vía IAM signBlob.
        credentials, _ = auth_default()
        credentials.refresh(Request())
        sa_email = getattr(credentials, "service_account_email", None)

        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=24),
            method="GET",
            service_account_email=sa_email,
            access_token=credentials.token,
        )

        return {
            "url": signed_url,
            "location_kind": "gcs_signed",
            "bucket": GCS_BUCKET,
            "filename": filename,
            "size_bytes": size,
            "expires_in_hours": 24,
        }

    # Local dev fallback
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / filename
    out_path.write_bytes(pdf_bytes)
    return {
        "url": f"file://{out_path}",
        "location_kind": "local",
        "path": str(out_path),
        "filename": filename,
        "size_bytes": size,
    }


# ---------- helpers (portados de producción) ----------

def _hex(h: str) -> colors.Color:
    try:
        return colors.HexColor(h)
    except Exception:
        return colors.HexColor("#1F6FEB")


def _eur(x: Any) -> str:
    if x is None or x == "":
        return "—"
    try:
        return f"{float(x):,.0f} €".replace(",", ".")
    except Exception:
        return "—"


def _pct(x: Any) -> str:
    if x is None:
        return "—"
    try:
        return f"{float(x):.1f}%"
    except Exception:
        return "—"


# Paleta semántica para recomendaciones — etiquetas en inglés (PDF EN).
_RECO_STYLE: dict[str, dict[str, str]] = {
    "muy_recomendado": {"bg": "#15803D", "fg": "#FFFFFF", "label": "HIGHLY RECOMMENDED"},
    "recomendado":     {"bg": "#22C55E", "fg": "#FFFFFF", "label": "RECOMMENDED"},
    "marginal":        {"bg": "#F59E0B", "fg": "#FFFFFF", "label": "MARGINAL"},
    "no_recomendado":  {"bg": "#DC2626", "fg": "#FFFFFF", "label": "NOT RECOMMENDED"},
}

# Traducción condiciones / kinds — para que la salida sea consistente en inglés.
_CONDITION_EN: dict[str, str] = {
    "nuevo": "new",
    "buen_estado": "good condition",
    "a_reformar": "to renovate",
}
_KIND_EN: dict[str, str] = {
    "salon": "living room",
    "master_bedroom": "master bedroom",
    "secondary_bedroom": "bedroom",
    "kids_bedroom": "kids bedroom",
    "kitchen": "kitchen",
    "bathroom": "bathroom",
    "dining_room": "dining room",
    "office": "office",
    "hallway": "hallway",
    "terrace": "terrace",
    "laundry": "laundry",
    "storage": "storage",
    "other": "other",
}


def _kpi_card(label: str, value: str, primary_hex: str, accent: bool = False) -> Table:
    """Bloque tipo KPI: etiqueta arriba pequeña, valor grande debajo."""
    bg = _hex(primary_hex) if accent else colors.HexColor("#F4F6FA")
    fg = colors.white if accent else _hex(primary_hex)
    label_color = colors.HexColor("#E5E7EB") if accent else colors.HexColor("#6B7280")
    inner = Table(
        [[label.upper()], [value]],
        colWidths=[52 * mm],
        rowHeights=[6 * mm, 14 * mm],
    )
    inner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("FONT", (0, 0), (0, 0), "Helvetica-Bold", 7),
        ("FONT", (0, 1), (0, 1), "Helvetica-Bold", 14),
        ("TEXTCOLOR", (0, 0), (0, 0), label_color),
        ("TEXTCOLOR", (0, 1), (0, 1), fg),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return inner


class _BrandedCanvas(rl_canvas.Canvas):
    """Canvas con branding mínimo + paginación. Estilo coherente con V1."""

    def __init__(self, *args, agency=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._agency = agency or {}
        self._saved_pages = []

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_pages) + 1
        for i, state in enumerate(self._saved_pages):
            self.__dict__.update(state)
            self._draw_branding(i + 1, total)
            rl_canvas.Canvas.showPage(self)
        self._draw_branding(total, total)
        rl_canvas.Canvas.save(self)

    def _draw_branding(self, page_num, total):
        primary = _hex(self._agency.get("primary_color", "#1F6FEB"))
        self.setStrokeColor(primary)
        self.setLineWidth(1.5)
        self.line(15 * mm, 285 * mm, 195 * mm, 285 * mm)
        self.setFillColor(colors.HexColor("#666666"))
        self.setFont("Helvetica", 8)
        contact = "  ·  ".join(
            c for c in [
                self._agency.get("name", ""),
                self._agency.get("contact_name", ""),
                self._agency.get("phone", ""),
                self._agency.get("email", ""),
            ] if c
        )
        self.drawString(15 * mm, 12 * mm, contact[:150])
        self.drawRightString(195 * mm, 12 * mm, f"Page {page_num} / {total}")
        self.setFont("Helvetica-Oblique", 7)
        self.setFillColor(colors.HexColor("#AAAAAA"))
        self.drawCentredString(
            105 * mm, 8 * mm,
            "Generated by Decomind Agent (Google Cloud · Gemini)",
        )


def _styles(primary_hex: str):
    ss = getSampleStyleSheet()
    primary = _hex(primary_hex)
    return {
        "h1": ParagraphStyle(
            "H1", parent=ss["Heading1"],
            fontSize=20, leading=24, textColor=primary, alignment=TA_LEFT,
            spaceBefore=4, spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "H2", parent=ss["Heading2"],
            fontSize=14, leading=18, textColor=primary, spaceBefore=8, spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "H3", parent=ss["Heading3"],
            fontSize=11, leading=14,
            textColor=colors.HexColor("#222222"),
            spaceBefore=6, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "Body", parent=ss["BodyText"],
            fontSize=10, leading=14, alignment=TA_LEFT,
        ),
        "small": ParagraphStyle(
            "Small", parent=ss["BodyText"],
            fontSize=8, leading=11, textColor=colors.HexColor("#555555"),
        ),
        "center_xl": ParagraphStyle(
            "CenterXL", parent=ss["Heading1"],
            fontSize=28, leading=32, alignment=TA_CENTER, textColor=primary,
        ),
    }


# ---------- tool ----------

@mcp.tool()
def render_dossier_pdf(
    property_address: str,
    property_municipality: str,
    property_district: str,
    property_surface_m2: float,
    property_year_built: int,
    property_condition: str,
    median_price_eur_per_m2: float,
    data_source: str,
    current_value_eur: float,
    post_reno_value_eur: float,
    renovation_total_integral_eur: float,
    renovation_tier: str,
    by_room: list[dict[str, Any]],
    roi_net_gain_eur: float,
    roi_payback_ratio: float,
    roi_recommendation: str,
    agent_verdict: str,
    property_features: list[str] | None = None,
    agency_name: str = "Decomind",
    agency_primary_color: str = "#1F6FEB",
    agency_contact: str = "",
    agency_phone: str = "",
    agency_email: str = "",
) -> dict[str, Any]:
    """Genera el PDF del dossier inmobiliario y lo guarda en disco local.

    Args:
        property_address: Calle y número (ej. "Calle Mayor 5").
        property_municipality: Municipio (ej. "Madrid").
        property_district: Distrito (ej. "Centro").
        property_surface_m2: Superficie del inmueble.
        property_year_built: Año de construcción.
        property_condition: "nuevo" | "buen_estado" | "a_reformar".
        median_price_eur_per_m2: Mediana €/m² de la zona (find_comparables).
        data_source: Origen del dato (mitma_municipal | curated_province | ...).
        current_value_eur: Valor actual estimado.
        post_reno_value_eur: Valor tras reforma.
        renovation_total_integral_eur: Coste total de la reforma (integral).
        renovation_tier: Tier (economy | standard | premium).
        by_room: Lista by_room devuelta por estimate_renovation_plan. Cada item:
            {"kind":"...","area_sqm":X,"painting":..,"masonry":..,
             "plumbing":..,"electrical":..,"labor":..,"total_integral":..}
        roi_net_gain_eur: Ganancia neta tras reforma.
        roi_payback_ratio: Ratio payback (revalorización / inversión).
        roi_recommendation: muy_recomendado | recomendado | marginal | no_recomendado.
        agent_verdict: 2-3 frases del agente con el veredicto final para el propietario.
        property_features: Lista de características extra a mostrar como chips en
            portada. Ej: ["Sin ascensor", "Certificación E", "Vistas al mar",
            "2 dormitorios", "1 baño"]. Opcional.
        agency_*: Branding white-label de la agencia inmobiliaria (opcional).

    Returns:
        {path, filename, pages_estimated, size_bytes}
    """
    ts = int(time.time())
    filename = f"dossier_{ts}.pdf"

    by_room = by_room or []

    agency = {
        "name": agency_name,
        "primary_color": agency_primary_color,
        "contact_name": agency_contact,
        "phone": agency_phone,
        "email": agency_email,
    }
    S = _styles(agency_primary_color)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=22 * mm, bottomMargin=22 * mm,
        title=f"Dossier {property_address}",
        author=agency_name,
    )

    story: list = []

    # ── Página 1: portada con hero ───────────────────────────────────────
    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph("VALUATION REPORT", S["center_xl"]))
    story.append(Paragraph(
        f"<para alignment='center'>{agency_name}</para>", S["h2"],
    ))
    story.append(Spacer(1, 10 * mm))

    # Hero block — current estimated value (large, in primary color)
    sub_location = property_municipality
    if property_district:
        sub_location += f"  ·  {property_district}"
    hero = Table(
        [
            ["ESTIMATED CURRENT VALUE"],
            [_eur(current_value_eur)],
            [f"{property_address}  ·  {sub_location}"],
        ],
        colWidths=[165 * mm],
        rowHeights=[8 * mm, 20 * mm, 7 * mm],
    )
    hero.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _hex(agency_primary_color)),
        ("FONT", (0, 0), (0, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (0, 1), "Helvetica-Bold", 30),
        ("FONT", (0, 2), (0, 2), "Helvetica", 10),
        ("TEXTCOLOR", (0, 0), (0, 0), colors.HexColor("#E5E7EB")),
        ("TEXTCOLOR", (0, 1), (0, 1), colors.white),
        ("TEXTCOLOR", (0, 2), (0, 2), colors.HexColor("#E5E7EB")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(hero)
    story.append(Spacer(1, 12 * mm))

    # Property data block
    story.append(Paragraph("Property details", S["h3"]))
    municipio_line = property_municipality
    if property_district:
        municipio_line += f"  ·  district {property_district}"
    cover_data = [
        ["Address", property_address],
        ["Municipality", municipio_line],
        ["Surface area", f"{property_surface_m2:.0f} m²"],
        ["Year built", str(property_year_built)],
        ["Current condition", _CONDITION_EN.get(property_condition, property_condition.replace("_", " "))],
    ]
    t = Table(cover_data, colWidths=[50 * mm, 115 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 10),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 10),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1),
         [colors.white, colors.HexColor("#F4F6FA")]),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#EEEEEE")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(t)

    # Optional extra-features chips
    if property_features:
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph("Additional features", S["h3"]))
        story.append(Spacer(1, 2 * mm))
        # construir fila de chips — máx 4 por fila para que respiren
        chip_rows: list[list] = []
        row: list = []
        for feat in property_features:
            chip = Table(
                [[str(feat)]],
                colWidths=[None],
                rowHeights=[7 * mm],
            )
            chip.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1),
                 colors.HexColor("#EEF2FF")),
                ("TEXTCOLOR", (0, 0), (-1, -1),
                 _hex(agency_primary_color)),
                ("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 8),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("BOX", (0, 0), (-1, -1), 0.5,
                 _hex(agency_primary_color)),
            ]))
            row.append(chip)
            if len(row) == 4:
                chip_rows.append(row)
                row = []
        if row:
            # rellenar para que la última fila no se deforme
            while len(row) < 4:
                row.append("")
            chip_rows.append(row)
        feat_table = Table(
            chip_rows,
            colWidths=[40 * mm, 40 * mm, 40 * mm, 40 * mm],
        )
        feat_table.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(feat_table)

    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph(
        f"Generated on <b>{time.strftime('%Y-%m-%d')}</b> by an autonomous agent "
        f"(Google ADK + Gemini · Vertex AI). All figures are computed in real time "
        f"through decoupled tools (MCP). This document is an orientative estimate "
        f"and does not constitute a binding offer.",
        S["small"],
    ))
    story.append(PageBreak())

    # ── Página 2: zona + valoración con KPI cards ────────────────────────
    story.append(Paragraph("1. Area analysis and valuation", S["h1"]))
    loc_line = f"Location: <b>{property_municipality}</b>"
    if property_district:
        loc_line += f", district <b>{property_district}</b>"
    loc_line += "."
    story.append(Paragraph(loc_line, S["body"]))
    story.append(Spacer(1, 6 * mm))

    # 3 KPI cards en fila — median €/m², current value (accent), post-reno value
    delta_eur = (post_reno_value_eur or 0) - (current_value_eur or 0)
    kpi_row = Table(
        [[
            _kpi_card("Area median €/m²", _eur(median_price_eur_per_m2),
                      agency_primary_color, accent=False),
            _kpi_card("Current value", _eur(current_value_eur),
                      agency_primary_color, accent=True),
            _kpi_card("Value after renovation", _eur(post_reno_value_eur),
                      agency_primary_color, accent=False),
        ]],
        colWidths=[57 * mm, 57 * mm, 57 * mm],
        rowHeights=[24 * mm],
    )
    kpi_row.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(kpi_row)
    story.append(Spacer(1, 4 * mm))

    # Delta band — potential uplift after renovation
    delta_color = colors.HexColor("#15803D" if delta_eur > 0 else "#DC2626")
    delta_band = Table(
        [[f"Potential uplift after renovation:  {_eur(delta_eur)}"]],
        colWidths=[171 * mm],
        rowHeights=[8 * mm],
    )
    delta_band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), delta_color),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 11),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(delta_band)
    story.append(Spacer(1, 8 * mm))

    # Explicit warning when data is a fallback (low confidence)
    if data_source == "fallback":
        warn = Table(
            [["⚠  Low confidence: this municipality is not covered by official "
              "sources. Valuation uses the national median."]],
            colWidths=[171 * mm],
            rowHeights=[10 * mm],
        )
        warn.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF3C7")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#92400E")),
            ("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 9),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#F59E0B")),
        ]))
        story.append(warn)
        story.append(Spacer(1, 6 * mm))

    # Data source and traceability
    story.append(Paragraph("Data source and traceability", S["h3"]))
    src_label = {
        "mitma_municipal": "Spanish Ministry of Transport (MITMA) — Housing "
                           "Appraisal Value, official municipal figure.",
        "curated_province": "Curated provincial median (INE / Tinsa / Notaries) "
                            "with district-level multiplier.",
        "mitma_province":   "Spanish Ministry of Transport (MITMA) — provincial "
                            "aggregate (median of municipalities).",
        "fallback":         "National estimate (this municipality could not be "
                            "matched to official sources).",
    }.get(data_source, data_source)
    story.append(Paragraph(src_label, S["body"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "<i>Individual comparables are synthetic samples generated from the "
        "official median. Known limitation: sub-municipal granularity (district, "
        "coastal premium, micro-zones) is not captured at this MVP stage. "
        "Production roadmap (M2) integrates Idealista Data and Tinsa API under "
        "commercial contract for real listings and finer geographic resolution.</i>",
        S["small"],
    ))
    story.append(PageBreak())

    # ── Page 3: renovation budget ────────────────────────────────────────
    tier_en = {"economy": "economy", "standard": "standard", "premium": "premium"}.get(
        renovation_tier, renovation_tier,
    )
    story.append(Paragraph(
        f"2. Renovation proposal — {tier_en} tier", S["h1"],
    ))
    if by_room:
        header = ["Room", "m²", "Paint", "Masonry", "Plumbing", "Electric", "Labor", "Total"]
        rows = [header]
        for r in by_room:
            kind_raw = str(r.get("kind", ""))
            rows.append([
                _KIND_EN.get(kind_raw, kind_raw.replace("_", " ")),
                f"{r.get('area_sqm', 0):.0f}",
                _eur(r.get("painting")),
                _eur(r.get("masonry")),
                _eur(r.get("plumbing")),
                _eur(r.get("electrical")),
                _eur(r.get("labor")),
                _eur(r.get("total_integral")),
            ])
        rows.append([
            "TOTAL", "", "", "", "", "", "",
            _eur(renovation_total_integral_eur),
        ])
        tb = Table(rows, colWidths=[28 * mm] + [10 * mm] + [22 * mm] * 6)
        tb.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
            ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 9),
            ("BACKGROUND", (0, 0), (-1, 0), _hex(agency_primary_color)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F0F3FA")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2),
             [colors.white, colors.HexColor("#FAFBFD")]),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(tb)
    else:
        story.append(Paragraph(
            "<i>No room-level breakdown provided.</i>", S["small"],
        ))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "<i>Orientative estimate based on average Spanish renovation rates "
        "(2026). Not a binding offer.</i>",
        S["small"],
    ))
    story.append(PageBreak())

    # ── Page 4: summary + ROI + verdict ──────────────────────────────────
    story.append(Paragraph("3. Investment summary and return", S["h1"]))

    # 3 KPI cards: investment, uplift, payback
    roi_kpis = Table(
        [[
            _kpi_card("Renovation investment",
                      _eur(renovation_total_integral_eur),
                      agency_primary_color),
            _kpi_card("Net uplift",
                      _eur(roi_net_gain_eur),
                      agency_primary_color, accent=True),
            _kpi_card("Payback ratio",
                      f"{roi_payback_ratio:.2f}×",
                      agency_primary_color),
        ]],
        colWidths=[57 * mm, 57 * mm, 57 * mm],
        rowHeights=[24 * mm],
    )
    roi_kpis.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(roi_kpis)
    story.append(Spacer(1, 8 * mm))

    # Badge de recomendación coloreado
    reco_style = _RECO_STYLE.get(
        roi_recommendation,
        {"bg": "#6B7280", "fg": "#FFFFFF", "label": roi_recommendation.upper()},
    )
    badge = Table(
        [[reco_style["label"]]],
        colWidths=[171 * mm],
        rowHeights=[14 * mm],
    )
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _hex(reco_style["bg"])),
        ("TEXTCOLOR", (0, 0), (-1, -1), _hex(reco_style["fg"])),
        ("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 16),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(badge)
    story.append(Spacer(1, 10 * mm))

    # Detailed breakdown (compact table below)
    summary_rows = [
        ["Current property value", _eur(current_value_eur)],
        ["Renovation investment", _eur(renovation_total_integral_eur)],
        ["Estimated value after renovation", _eur(post_reno_value_eur)],
        ["Net uplift", _eur(roi_net_gain_eur)],
        ["Payback ratio", f"{roi_payback_ratio:.2f}×"],
    ]
    ts_ = Table(summary_rows, colWidths=[105 * mm, 60 * mm])
    ts_.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1),
         [colors.white, colors.HexColor("#F4F6FA")]),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#EEEEEE")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(ts_)
    story.append(Spacer(1, 10 * mm))

    # Verdict — bordered box
    story.append(Paragraph("Agent verdict", S["h2"]))
    verdict_box = Table(
        [[Paragraph(agent_verdict or "—", S["body"])]],
        colWidths=[171 * mm],
    )
    verdict_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F9FAFB")),
        ("BOX", (0, 0), (-1, -1), 1, _hex(agency_primary_color)),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(verdict_box)

    # build → BytesIO
    doc.build(
        story,
        canvasmaker=lambda *a, **kw: _BrandedCanvas(*a, agency=agency, **kw),
    )

    pdf_bytes = buf.getvalue()
    result = _persist_pdf(pdf_bytes, filename)
    result["pages_estimated"] = 4
    return result


if __name__ == "__main__":
    from mcp_servers._runtime import run_server
    run_server(mcp)

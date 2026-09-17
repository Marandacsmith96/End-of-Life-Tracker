"""Build the vet summary PDF with ReportLab."""
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    CondPageBreak,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from . import charts, pdf_charts
from .entries import Entry, Medication
from .flags import Flag
from .models import Animal
from .scoring import ACCEPTABLE_TOTAL, CATEGORIES, MAX_TOTAL

SHORT_APPETITE = {"none": "Not eating", "low": "Less", "normal": "Normal", "high": "More"}

INK = colors.HexColor("#2b2b2b")
MUTED = colors.HexColor("#6b6b6b")
ACCENT = colors.HexColor("#3b6347")
BORDER = colors.HexColor("#e0ddd5")
LOW = colors.HexColor("#a33333")
WARN_BG = colors.HexColor("#fdf6e7")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=18, leading=22,
                                alignment=TA_LEFT, textColor=INK, spaceAfter=2),
        "sub": ParagraphStyle("s", parent=base["Normal"], fontSize=9.5, textColor=MUTED,
                              leading=13),
        "h2": ParagraphStyle("h", parent=base["Heading2"], fontSize=12, leading=15,
                             textColor=INK, spaceBefore=12, spaceAfter=4),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9.5, leading=13,
                               textColor=INK),
        "small": ParagraphStyle("sm", parent=base["Normal"], fontSize=8, leading=10,
                                textColor=MUTED),
        "cell": ParagraphStyle("c", parent=base["Normal"], fontSize=8, leading=10,
                               textColor=INK),
        "flag": ParagraphStyle("f", parent=base["Normal"], fontSize=9, leading=12,
                               textColor=INK),
    }


def _fmt(day: date) -> str:
    return f"{day:%b} {day.day}, {day.year}"


def _esc(text: str | None) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_pdf(
    animal: Animal,
    entries: list[Entry],
    medications: list[Medication],
    flags: list[Flag],
    med_names: dict[int, list[str]],
    start: date | None,
    end: date,
    generated: date | None = None,
) -> bytes:
    """Return the PDF bytes for one animal over a date range."""
    st = _styles()
    generated = generated or date.today()
    ordered = sorted(entries, key=lambda e: e.entry_date)
    series = charts.build_series(ordered)
    summary = charts.summarize(ordered)
    dates = [e.entry_date for e in ordered]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        title=f"{animal.name} quality-of-life summary", author="Pet Quality-of-Life Tracker",
    )
    width = doc.width
    story = []

    # Header
    details = [animal.species.capitalize()]
    if animal.breed:
        details.append(_esc(animal.breed))
    if animal.age_text:
        details.append(animal.age_text)
    range_text = f"{_fmt(start)} to {_fmt(end)}" if start else f"All entries through {_fmt(end)}"
    story.append(Paragraph(f"{_esc(animal.name)}: quality-of-life summary", st["title"]))
    story.append(Paragraph(" · ".join(details), st["sub"]))
    story.append(Paragraph(
        f"{range_text} · {summary.get('count', 0)} entries · prepared {_fmt(generated)} "
        f"by the owner using the HHHHHMM scale (each of 7 areas scored 0–10, total out of {MAX_TOTAL}).",
        st["sub"]))
    story.append(Spacer(1, 8))

    if not ordered:
        story.append(Paragraph("No entries were logged in this range.", st["body"]))
        doc.build(story)
        return buf.getvalue()

    # Summary tiles as a table
    latest_color = "#a33333" if summary["latest_total"] <= ACCEPTABLE_TOTAL else "#3b6347"
    tiles = [
        ("Latest total", f"{summary['latest_total']} / {MAX_TOTAL}", _fmt(summary["latest_date"]), latest_color),
        ("Average", f"{summary['average']}", f"over {summary['count']} entries", "#2b2b2b"),
        ("Range", f"{summary['lowest']}–{summary['highest']}", "lowest to highest", "#2b2b2b"),
        ("Trend", f"{summary['trend']:+}", "last week vs first week", "#2b2b2b"),
    ]
    cells = [[
        Paragraph(
            f"<font size=8 color='#6b6b6b'>{label}</font><br/>"
            f"<font size=14 color='{color}'><b>{value}</b></font><br/>"
            f"<font size=7.5 color='#6b6b6b'>{note}</font>", st["body"])
        for label, value, note, color in tiles
    ]]
    tile_table = Table(cells, colWidths=[width / 4] * 4)
    tile_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tile_table)

    # Flags
    if flags:
        story.append(Paragraph("Patterns to discuss", st["h2"]))
        rows = [[Paragraph(f"<b>{_esc(f.title)}</b><br/>{_esc(f.detail)}", st["flag"])] for f in flags]
        flag_table = Table(rows, colWidths=[width])
        flag_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), WARN_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2b96f")),
            ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.white),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(flag_table)
        story.append(Paragraph(
            "These are patterns in what the owner logged, not a diagnosis.", st["small"]))

    # Charts
    story.append(Paragraph("Total score over time", st["h2"]))
    story.append(Paragraph(
        f"The dashed line marks {ACCEPTABLE_TOTAL}, the threshold the scale usually cites.", st["small"]))
    story.append(_image(pdf_charts.total_chart(dates, series["total"]), width))

    story.append(Paragraph("By category", st["h2"]))
    story.append(_image(pdf_charts.category_charts(dates, series["categories"]), width))

    if series["weight"]["unit"]:
        story.append(KeepTogether([
            Paragraph(f"Weight ({series['weight']['unit']})", st["h2"]),
            _image(pdf_charts.weight_chart(dates, series["weight"]["values"], series["weight"]["unit"]), width),
        ]))

    # Medications
    if medications:
        story.append(Paragraph("Medications", st["h2"]))
        med_rows = [["Name", "Dose", "Schedule", "Status"]] + [
            [_esc(m.name), _esc(m.dose), _esc(m.schedule), "Active" if m.active else "Stopped"]
            for m in medications
        ]
        story.append(_table(med_rows, [width * 0.3, width * 0.2, width * 0.35, width * 0.15], st))

    # Daily table
    story.append(CondPageBreak(3 * inch))
    story.append(Paragraph("Daily entries", st["h2"]))
    short = {"hurt": "Hurt", "hunger": "Hung", "hydration": "Hydr", "hygiene": "Hyg",
             "happiness": "Happy", "mobility": "Mob", "good_days": "Good"}
    header = ["Date", "Total"] + [short[k] for k, _, _ in CATEGORIES] + ["Weight", "Appetite", "Meds given"]
    rows = [header]
    for e in sorted(ordered, key=lambda e: e.entry_date, reverse=True):
        weight = f"{e.weight:g} {e.weight_unit}" if e.weight is not None else ""
        rows.append([
            f"{e.entry_date:%b} {e.entry_date.day}", str(e.total),
            *[str(e.scores[k]) for k, _, _ in CATEGORIES],
            weight, SHORT_APPETITE.get(e.appetite, ""),
            Paragraph(_esc(", ".join(med_names.get(e.id, []))), st["cell"]),
        ])
    col = [0.62, 0.45] + [0.42] * 7 + [0.62, 0.75]
    col_widths = [c * inch for c in col] + [width - sum(col) * inch]
    table = _table(rows, col_widths, st, repeat=True)
    for i, e in enumerate(sorted(ordered, key=lambda e: e.entry_date, reverse=True), start=1):
        if e.total <= ACCEPTABLE_TOTAL:
            table.setStyle(TableStyle([("TEXTCOLOR", (1, i), (1, i), LOW)]))
    story.append(table)

    # Notes
    noted = [e for e in sorted(ordered, key=lambda e: e.entry_date, reverse=True) if e.notes]
    if noted:
        story.append(Paragraph("Owner's notes", st["h2"]))
        for e in noted:
            story.append(Paragraph(f"<b>{_fmt(e.entry_date)}</b> — {_esc(e.notes)}", st["body"]))
            story.append(Spacer(1, 3))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Scale: HHHHHMM (Hurt, Hunger, Hydration, Hygiene, Happiness, Mobility, More good days than bad), "
        "Villalobos. Scores are the owner's daily impressions.", st["small"]))

    doc.build(story)
    return buf.getvalue()


def _image(png: bytes, width: float) -> Image:
    img = Image(io.BytesIO(png))
    ratio = img.imageHeight / img.imageWidth
    img.drawWidth = width
    img.drawHeight = width * ratio
    return img


def _table(rows, col_widths, st, repeat=False) -> Table:
    table = Table(rows, colWidths=col_widths, repeatRows=1 if repeat else 0)
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEADING", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, BORDER),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table

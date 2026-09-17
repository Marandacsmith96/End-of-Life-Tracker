"""The one-page vet summary (ReportLab), with an optional appendix."""
import io
from datetime import date, timedelta

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    CondPageBreak, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from . import analytics as an
from . import charts, insights, pdf_charts, safety
from .entries import DAY_STATUS_LABELS, Entry, Medication
from .models import Animal
from .scoring import ATTRIBUTION, CATEGORIES

INK = colors.HexColor("#1d2637")
MUTED = colors.HexColor("#5c6b84")
ACCENT = colors.HexColor("#2e4e9f")
BORDER = colors.HexColor("#dfe5f0")
SOFT = colors.HexColor("#eef2f9")
WARN_BG = colors.HexColor("#fbf3e2")
WARN_BORDER = colors.HexColor("#ecd7a6")


def _styles():
    base = getSampleStyleSheet()
    def mk(name, **kw):
        kw.setdefault("textColor", INK)
        return ParagraphStyle(name, parent=base["Normal"], **kw)
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=16, leading=19, alignment=TA_LEFT,
                                textColor=INK, spaceAfter=1),
        "sub": mk("s", fontSize=8.5, leading=11, textColor=MUTED),
        "h2": mk("h", fontSize=9.5, leading=11, spaceBefore=5, spaceAfter=2, fontName="Helvetica-Bold"),
        "body": mk("b", fontSize=8.5, leading=11),
        "small": mk("sm", fontSize=7.2, leading=9, textColor=MUTED),
        "cell": mk("c", fontSize=7.5, leading=9.5),
        "bullet": mk("bl", fontSize=8.5, leading=11, leftIndent=9, bulletIndent=0),
    }


def _fmt(day: date) -> str:
    return f"{day:%b} {day.day}, {day.year}"


def _esc(text) -> str:
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _image(png: bytes, width: float) -> Image:
    img = Image(io.BytesIO(png))
    img.drawHeight = width * img.imageHeight / img.imageWidth
    img.drawWidth = width
    return img


def _table(rows, widths, st, header=True) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("LEADING", (0, 0), (-1, -1), 9.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, BORDER),
    ]
    if header:
        style += [("TEXTCOLOR", (0, 0), (-1, 0), MUTED), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                  ("LINEBELOW", (0, 0), (-1, 0), 0.6, BORDER)]
    t.setStyle(TableStyle(style))
    return t


def build_pdf(animal: Animal, entries: list[Entry], all_entries: list[Entry], medications: list[Medication],
              markers, responses: dict, baseline, events, start: date | None, end: date,
              include_appendix: bool = False, generated: date | None = None) -> bytes:
    st = _styles()
    generated = generated or date.today()
    ordered = sorted(entries, key=lambda e: e.entry_date)
    chart_start = start or (ordered[0].entry_date if ordered else end - timedelta(days=29))
    series = charts.build_series(ordered, start, end, baseline, events)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.45 * inch, bottomMargin=0.45 * inch,
                            title=f"{animal.name} quality-of-life summary", author="Quality-of-Life Tracker")
    width = doc.width
    story = []

    # Header -----------------------------------------------------------------
    details = [animal.species.capitalize()]
    if animal.breed:
        details.append(_esc(animal.breed))
    if animal.sex and animal.sex != "unknown":
        details.append(animal.sex)
    if animal.age_text:
        details.append(animal.age_text)
    range_text = f"{_fmt(start)} to {_fmt(end)}" if start else f"All entries through {_fmt(end)}"
    story.append(Paragraph(f"{_esc(animal.name)}: quality-of-life summary", st["title"]))
    story.append(Paragraph(" · ".join(details), st["sub"]))
    story.append(Paragraph(f"{range_text} · {len(ordered)} check-ins · generated {_fmt(generated)}", st["sub"]))
    if animal.diagnoses:
        story.append(Paragraph(f"Diagnoses (as entered by owner): {_esc(animal.diagnoses)}", st["sub"]))
    story.append(Paragraph(safety.REPORT_NOTE, st["small"]))
    story.append(Spacer(1, 5))

    if not ordered:
        story.append(Paragraph("No check-ins were recorded in this range.", st["body"]))
        doc.build(story)
        return buf.getvalue()

    # Top row: tiles ---------------------------------------------------------
    points = an.overall_points(all_entries)
    comp = an.period_comparison(points, end, recent_days=14, previous_days=28)
    counts = an.day_counts(ordered, chart_start, end)
    prev_counts = an.day_counts(all_entries, chart_start - timedelta(days=(end - chart_start).days + 1),
                                chart_start - timedelta(days=1))
    cls, trend_text = insights.trend_summary(all_entries, end, animal.name)
    tiles = [
        ("Recent score (14 days)", f"{comp.recent_mean:.1f} / 10" if comp.recent_mean is not None else "—",
         f"{comp.recent_n} scored days"),
        ("Previous 28 days", f"{comp.previous_mean:.1f} / 10" if comp.previous_mean is not None else "—",
         f"{comp.previous_n} scored days"),
        ("Good / mixed / bad", f"{counts.good} / {counts.mixed} / {counts.bad}",
         f"{counts.not_logged} not logged" + (f"; before: {prev_counts.good}/{prev_counts.mixed}/{prev_counts.bad}" if prev_counts.logged else "")),
        ("Baseline (owner estimate)", f"{baseline.mean:.1f} / 10" if baseline and baseline.mean is not None else "—",
         baseline.label.replace("Owner-estimated baseline — ", "") if baseline else "not entered"),
    ]
    cells = [[Paragraph(f"<font size=7 color='#5c6b84'>{_esc(l)}</font><br/><font size=12><b>{_esc(v)}</b></font><br/>"
                        f"<font size=6.5 color='#5c6b84'>{_esc(n)}</font>", st["body"]) for l, v, n in tiles]]
    t = Table(cells, colWidths=[width / 4] * 4)
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, BORDER), ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.append(t)

    # Trend chart --------------------------------------------------------------
    story.append(Paragraph("Quality-of-life trend", st["h2"]))
    story.append(_image(pdf_charts.trend_chart(series, chart_start, end), width))
    story.append(Paragraph(safety.guard(trend_text) + " " + cls.sufficiency.text, st["small"]))
    story.append(_image(pdf_charts.days_strip({e.entry_date: e.day_status for e in ordered}, chart_start, end), width))
    story.append(Paragraph("Good, mixed, and bad days across the range (grey = not logged).", st["small"]))

    # Two columns: category table + behaviors ---------------------------------
    cat_rows = [["Category", "Recent 14d", "Prev 28d", "Baseline"]]
    for key, label, *_ in CATEGORIES:
        c = an.period_comparison(an.category_points(all_entries, key), end, recent_days=14, previous_days=28)
        base = getattr(baseline, key) if baseline else None
        cat_rows.append([label if len(label) < 20 else "Good days > bad",
                         f"{c.recent_mean:.1f}" if c.recent_mean is not None else "—",
                         f"{c.previous_mean:.1f}" if c.previous_mean is not None else "—",
                         f"{base}" if base is not None else "—"])
    cat_table = _table(cat_rows, [1.35 * inch, 0.7 * inch, 0.7 * inch, 0.6 * inch], st)

    right = []
    rates = an.marker_rates(all_entries, responses, markers, end - timedelta(days=29), end)
    prev_rates = {r.marker_id: r for r in an.marker_rates(all_entries, responses, markers,
                                                          end - timedelta(days=59), end - timedelta(days=30))}
    if rates:
        rows = [["Good-day behavior", "Last 30d", "Prev 30d"]]
        for r in rates:
            p = prev_rates.get(r.marker_id)
            rows.append([Paragraph(_esc(r.label), st["cell"]), f"{r.pct}%" if r.pct is not None else "—",
                         f"{p.pct}%" if p and p.pct is not None else "—"])
        right.append(_table(rows, [1.9 * inch, 0.6 * inch, 0.6 * inch], st))
    else:
        right.append(Paragraph("No personalized behaviors set up.", st["small"]))
    two = Table([[[Paragraph("Scores by category (0–10)", st["h2"]), cat_table],
                  [Paragraph("Behaviors (share of logged days)", st["h2"]), *right]]],
                colWidths=[width * 0.5, width * 0.5])
    two.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (0, 0), 8)]))
    story.append(two)

    # Notable changes ----------------------------------------------------------
    bullets = insights.discussion_points(all_entries, end, animal.name, markers, responses, baseline, events)
    story.append(Paragraph("Notable changes in the recorded observations", st["h2"]))
    if bullets:
        rows = [[Paragraph("• " + _esc(b), st["body"])] for b in bullets[:6]]
        t = Table(rows, colWidths=[width])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARN_BG), ("BOX", (0, 0), (-1, -1), 0.5, WARN_BORDER),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(t)
    else:
        story.append(Paragraph("Nothing stands out in the recorded observations for this period.", st["body"]))

    # Events + medications side by side ----------------------------------------
    left_items = [Paragraph("Events", st["h2"])]
    if events:
        rows = [[f"{e.event_date:%b} {e.event_date.day}", Paragraph(f"{_esc(e.title)} <font color='#5c6b84'>({_esc(e.type_label)})</font>", st["cell"])]
                for e in sorted(events, key=lambda e: e.event_date, reverse=True)[:8]]
        left_items.append(_table(rows, [0.6 * inch, 2.8 * inch], st, header=False))
    else:
        left_items.append(Paragraph("None recorded in this range.", st["small"]))
    right_items = [Paragraph("Medications (as entered by owner)", st["h2"])]
    if medications:
        rows = [[Paragraph(f"{_esc(m.name)}{(' · ' + _esc(m.dose)) if m.dose else ''}{(' · ' + _esc(m.schedule)) if m.schedule else ''}", st["cell"]),
                 "Active" if m.active else "Stopped"] for m in medications[:8]]
        right_items.append(_table(rows, [2.7 * inch, 0.7 * inch], st, header=False))
    else:
        right_items.append(Paragraph("None entered.", st["small"]))
    two = Table([[left_items, right_items]], colWidths=[width * 0.5, width * 0.5])
    two.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (0, 0), 8)]))
    story.append(two)

    story.append(Spacer(1, 4))
    story.append(Paragraph(ATTRIBUTION + " " + safety.DISCLAIMER, st["small"]))

    # Appendix ---------------------------------------------------------------
    if include_appendix:
        story.append(PageBreak())
        story.append(Paragraph("Appendix: category detail", st["h2"]))
        story.append(_image(pdf_charts.category_charts(series, chart_start, end), width))
        story.append(CondPageBreak(2.5 * inch))
        story.append(Paragraph("Appendix: daily check-ins", st["h2"]))
        short = {"hurt": "Hurt", "hunger": "Hung", "hydration": "Hydr", "hygiene": "Hyg",
                 "happiness": "Happy", "mobility": "Mob", "good_days": "Good"}
        header = ["Date", "Day", "Avg"] + [short[k] for k, *_ in CATEGORIES] + ["Weight", "Note"]
        rows = [header]
        for e in sorted(ordered, key=lambda e: e.entry_date, reverse=True):
            rows.append([f"{e.entry_date:%b} {e.entry_date.day}",
                         DAY_STATUS_LABELS.get(e.day_status, "")[:5] if e.day_status else "",
                         f"{e.mean:.1f}" if e.mean is not None else "",
                         *["" if e.scores[k] is None else str(e.scores[k]) for k, *_ in CATEGORIES],
                         f"{e.weight:g} {e.weight_unit}" if e.weight is not None else "",
                         Paragraph(_esc(e.notes), st["cell"])])
        widths = [0.55, 0.45, 0.4] + [0.38] * 7 + [0.6]
        story.append(_table(rows, [w * inch for w in widths] + [width - sum(widths) * inch], st))
        notes = [c for c in [] ]  # caregiver notes are deliberately not included
        del notes

    doc.build(story)
    return buf.getvalue()

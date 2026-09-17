from datetime import date, timedelta

from pypdf import PdfReader
import io

from app import pdf, pdf_charts
from app.entries import Entry, Medication
from app.flags import Flag
from app.models import Animal

KEYS = ("hurt", "hunger", "hydration", "hygiene", "happiness", "mobility", "good_days")
TODAY = date(2026, 9, 17)


def _entry(days_ago, each=6, weight=None, notes=None):
    return Entry(id=days_ago, animal_id=1, entry_date=TODAY - timedelta(days=days_ago),
                 weight=weight, weight_unit="kg" if weight else None, appetite="normal",
                 notes=notes, **{k: each for k in KEYS})


ANIMAL = Animal(1, "Biscuit & Co <3", "dog", "Beagle", date(2012, 8, 11), None, False)


def test_chart_images_are_png():
    dates = [TODAY - timedelta(days=i) for i in range(10)][::-1]
    assert pdf_charts.total_chart(dates, [40] * 10)[:8] == b"\x89PNG\r\n\x1a\n"
    cats = [{"key": k, "label": k, "values": [5] * 10} for k in KEYS]
    assert pdf_charts.category_charts(dates, cats)[:8] == b"\x89PNG\r\n\x1a\n"
    assert pdf_charts.weight_chart(dates, [10.0, None] * 5, "kg")[:8] == b"\x89PNG\r\n\x1a\n"


def test_build_pdf_full_report():
    entries = [_entry(i, each=5 if i < 3 else 7, weight=10 - i * 0.05, notes="Slept well" if i % 4 == 0 else None)
               for i in range(20)]
    meds = [Medication(1, 1, "Gabapentin", "100 mg", "twice daily", True)]
    flags = [Flag("low_total", "watch", "Total score at or below 35", "Detail & more.")]
    data = pdf.build_pdf(ANIMAL, entries, meds, flags, {0: ["Gabapentin"]},
                         TODAY - timedelta(days=29), TODAY, generated=TODAY)
    assert data[:5] == b"%PDF-"
    reader = PdfReader(io.BytesIO(data))
    assert len(reader.pages) >= 2
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Biscuit & Co <3: quality-of-life summary" in text
    assert "Patterns to discuss" in text
    assert "Total score at or below 35" in text
    assert "Gabapentin" in text
    assert "Daily entries" in text
    assert "Owner's notes" in text
    assert "Slept well" in text
    assert "not a diagnosis" in text


def test_build_pdf_with_no_entries():
    data = pdf.build_pdf(ANIMAL, [], [], [], {}, None, TODAY, generated=TODAY)
    text = PdfReader(io.BytesIO(data)).pages[0].extract_text()
    assert "No entries were logged" in text


def test_export_routes(client):
    client.post("/animals/new", data={"name": "Mochi", "species": "cat"})
    for i in range(3):
        day = (date.today() - timedelta(days=i)).isoformat()
        client.post("/animals/1/log", data={"entry_date": day, **{k: 6 for k in KEYS}})
    page = client.get("/animals/1/export?range=14")
    assert page.status_code == 200
    assert b"3 entries in the selected range" in page.data

    response = client.get("/animals/1/export.pdf?range=14&download=1")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert "attachment" in response.headers["Content-Disposition"]
    assert "Mochi-quality-of-life-" in response.headers["Content-Disposition"]
    assert response.data[:5] == b"%PDF-"

    inline = client.get("/animals/1/export.pdf?range=14")
    assert "attachment" not in inline.headers.get("Content-Disposition", "")

    assert client.get("/animals/99/export.pdf").status_code == 404

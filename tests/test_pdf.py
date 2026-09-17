import io
from datetime import date, timedelta

from pypdf import PdfReader

from app import pdf, safety
from app.baseline import Baseline
from app.entries import Entry, Medication
from app.events import Event
from app.models import Animal

KEYS = ("hurt", "hunger", "hydration", "hygiene", "happiness", "mobility", "good_days")
TODAY = date(2026, 9, 17)
ANIMAL = Animal(1, "Maggie & Co <3", "dog", "Golden Retriever", "female", date(2013, 7, 1), None,
                "Arthritis", "active", None, "daily")


class M:
    def __init__(self, id, label): self.id, self.label = id, label


def _entry(days_ago, each=6, status="good", notes=None, weight=None):
    return Entry(id=1000 - days_ago, animal_id=1, entry_date=TODAY - timedelta(days=days_ago), day_status=status,
                 weight=weight, weight_unit="kg" if weight else None, appetite=None, notes=notes, **{k: each for k in KEYS})


def _text(data):
    reader = PdfReader(io.BytesIO(data))
    return reader, "\n".join(p.extract_text() for p in reader.pages)


def test_one_page_summary():
    entries = [_entry(d, 8 if d > 20 else 5, "good" if d > 20 else "bad", notes="x" if d % 5 == 0 else None,
                      weight=30 - d * 0.05) for d in range(60)]
    responses = {e.id: {1: (TODAY - e.entry_date).days > 25, 2: True} for e in entries}
    data = pdf.build_pdf(
        ANIMAL, entries, entries, [Medication(1, 1, "Gabapentin", "100 mg", "twice daily", None, None, True)],
        [M(1, "Gets onto the couch herself"), M(2, "Finishes dinner")], responses,
        Baseline(1, date(2026, 3, 1), 8, 9, 9, 9, 9, 8, 9, "mostly_good", "most_days", None),
        [Event(1, 1, TODAY - timedelta(days=20), "pain_medication_started", "Started gabapentin", None)],
        TODAY - timedelta(days=59), TODAY, generated=TODAY)
    reader, text = _text(data)
    assert len(reader.pages) == 1
    assert "Maggie & Co <3: quality-of-life summary" in text
    assert "Golden Retriever" in text and "Arthritis" in text
    assert "Gabapentin" in text and "Gets onto the couch herself" in text
    assert "Notable changes" in text
    assert "This report summarizes observations entered by the pet's caregiver" in text
    assert "Villalobos" in text
    flat = " ".join(text.split())
    assert safety.is_safe(flat.replace(safety.DISCLAIMER, ""))  # only the fixed disclaimer names euthanasia


def test_appendix_adds_pages():
    entries = [_entry(d, 6, notes="A note") for d in range(20)]
    data = pdf.build_pdf(ANIMAL, entries, entries, [], [], {}, None, [], TODAY - timedelta(days=19), TODAY,
                         include_appendix=True, generated=TODAY)
    reader, text = _text(data)
    assert len(reader.pages) >= 2 and "Appendix: daily check-ins" in text and "A note" in text


def test_empty_range():
    data = pdf.build_pdf(ANIMAL, [], [], [], [], {}, None, [], None, TODAY, generated=TODAY)
    assert "No check-ins were recorded" in _text(data)[1]


def test_export_routes(client):
    client.post("/animals/new", data={"name": "Mochi", "species": "cat"})
    for i in range(3):
        client.post("/animals/1/checkin", data={"entry_date": (date.today() - timedelta(days=i)).isoformat(),
                                                "day_status": "good", "scores_included": "1", **{k: 6 for k in KEYS}})
    response = client.get("/animals/1/export.pdf?range=30&download=1")
    assert response.status_code == 200 and response.mimetype == "application/pdf"
    assert "attachment" in response.headers["Content-Disposition"] and "Mochi-quality-of-life-" in response.headers["Content-Disposition"]
    assert "attachment" not in client.get("/animals/1/export.pdf?range=30").headers.get("Content-Disposition", "")
    assert client.get("/animals/99/export.pdf").status_code == 404

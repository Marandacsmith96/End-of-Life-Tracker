from datetime import date, timedelta

from app import charts
from app.entries import Entry


def _entry(day: date, total_each=5, weight=None, unit=None, **scores):
    values = {k: total_each for k in ("hurt", "hunger", "hydration", "hygiene", "happiness", "mobility", "good_days")}
    values.update(scores)
    return Entry(id=day.toordinal(), animal_id=1, entry_date=day, weight=weight, weight_unit=unit,
                 appetite=None, notes=None, **values)


TODAY = date(2026, 9, 17)


def test_resolve_range_presets():
    start, end, preset = charts.resolve_range("30", None, None, today=TODAY)
    assert (start, end, preset) == (TODAY - timedelta(days=29), TODAY, "30")
    start, end, preset = charts.resolve_range("all", None, None, today=TODAY)
    assert (start, end, preset) == (None, TODAY, "all")
    start, end, preset = charts.resolve_range("bogus", None, None, today=TODAY)
    assert preset == "30"


def test_resolve_range_custom_and_swapped():
    start, end, preset = charts.resolve_range(None, "2026-09-10", "2026-09-01", today=TODAY)
    assert (start, end, preset) == (date(2026, 9, 1), date(2026, 9, 10), "custom")


def test_build_series_orders_oldest_first_and_converts_weight():
    entries = [
        _entry(TODAY, weight=10, unit="lb"),
        _entry(TODAY - timedelta(days=1), weight=4.6, unit="kg", hurt=2),
        _entry(TODAY - timedelta(days=2)),
    ]
    series = charts.build_series(entries)
    assert series["labels"] == ["2026-09-15", "2026-09-16", "2026-09-17"]
    assert series["total"] == [35, 32, 35]
    assert series["categories"][0]["key"] == "hurt"
    assert series["categories"][0]["values"] == [5, 2, 5]
    assert series["weight"]["unit"] == "lb"  # most recent unit wins
    assert series["weight"]["values"][0] is None
    assert series["weight"]["values"][1] == round(4.6 / charts.KG_PER_LB, 2)
    assert series["weight"]["values"][2] == 10


def test_build_series_with_no_weights():
    series = charts.build_series([_entry(TODAY)])
    assert series["weight"] == {"unit": None, "values": [None]}


def test_summarize():
    assert charts.summarize([]) == {"count": 0}
    entries = [_entry(TODAY - timedelta(days=i), total_each=5 + (i % 2)) for i in range(4)]
    summary = charts.summarize(entries)
    assert summary["count"] == 4
    assert summary["latest_date"] == TODAY
    assert summary["latest_total"] == 35
    assert summary["lowest"] == 35 and summary["highest"] == 42
    assert summary["average"] == 38.5


def test_history_page_renders_charts_and_table(client):
    client.post("/animals/new", data={"name": "Mochi", "species": "cat"})
    for i in range(3):
        day = (date.today() - timedelta(days=i)).isoformat()
        client.post("/animals/1/log", data={
            "entry_date": day, "hurt": 7, "hunger": 6, "hydration": 8, "hygiene": 9,
            "happiness": 5, "mobility": 4, "good_days": 6, "weight": "4.2", "weight_unit": "kg",
        })
    response = client.get("/animals/1/history?range=14")
    assert response.status_code == 200
    body = response.data.decode()
    assert 'id="chart-total"' in body
    assert 'id="chart-mobility"' in body
    assert 'id="chart-weight"' in body
    assert "vendor/chart.umd.min.js" in body
    assert body.count("<tr>") == 4  # header + 3 rows
    assert '"total": [45, 45, 45]' in body


def test_history_page_empty_range(client):
    client.post("/animals/new", data={"name": "Mochi", "species": "cat"})
    response = client.get("/animals/1/history?start=2000-01-01&end=2000-01-31")
    assert b"No entries in this range" in response.data


def test_chart_js_is_served_locally(client):
    response = client.get("/static/vendor/chart.umd.min.js")
    assert response.status_code == 200
    assert b"Chart.js v4" in response.data[:200]

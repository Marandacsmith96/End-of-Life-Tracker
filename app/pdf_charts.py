"""Chart images for the PDF, drawn with matplotlib to match the on-screen charts."""
import io
from datetime import date, timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

SERIES = "#3d64c4"
POINT = "#3d64c4"
FAINT = "#9aa7bd"
GRID = "#dfe5f0"
INK = "#1d2637"
MUTED = "#5c6b84"
GOOD, MIXED, BAD = "#2f7d5b", "#8a6d1f", "#b6485f"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.titlecolor": INK, "axes.titlesize": 9,
    "axes.titleweight": "bold", "axes.titlelocation": "left",
})


def _style(ax, start: date, end: date, max_ticks: int = 8):
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.set_xlim(start - timedelta(days=1), end + timedelta(days=1))
    span = (end - start).days or 1
    fmt = mdates.DateFormatter("%b") if span > 180 else FuncFormatter(
        lambda x, _: f"{mdates.num2date(x):%b} {mdates.num2date(x).day}")
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=2, maxticks=max_ticks))
    ax.xaxis.set_major_formatter(fmt)


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def trend_chart(series: dict, start: date, end: date) -> bytes:
    """Raw daily scores as dots, the 7-day windowed mean as a line, baseline dashed, events as ticks."""
    o = series["overall"]
    dates = [date.fromisoformat(x) for x in o["dates"]]
    fig, ax = plt.subplots(figsize=(7.2, 1.95))
    ax.scatter(dates, o["values"], s=9, color=POINT, alpha=0.45, linewidths=0, label="Daily score", zorder=3)
    limited = o.get("sufficiency") != "adequate"
    # Draw the smoothed line only across consecutive non-None values.
    xs, ys = [], []
    for dt, val in zip(dates, o["smoothed"]):
        if val is None:
            if xs:
                ax.plot(xs, ys, color=SERIES, linewidth=1.2 if limited else 1.9, alpha=0.5 if limited else 1, zorder=4)
            xs, ys = [], []
        else:
            xs.append(dt); ys.append(val)
    if xs:
        ax.plot(xs, ys, color=SERIES, linewidth=1.2 if limited else 1.9, alpha=0.5 if limited else 1,
                label="7-day average", zorder=4)
    if series.get("baseline"):
        ax.axhline(series["baseline"]["value"], color=FAINT, linewidth=1, linestyle=(0, (5, 4)),
                   label="Owner-estimated baseline")
    for i, ev in enumerate(sorted(series.get("events", []), key=lambda e: e["date"])):
        when = date.fromisoformat(ev["date"])
        ax.axvline(when, color=FAINT, linewidth=0.8, linestyle=(0, (2, 3)), zorder=1)
        ax.text(when, 9.8 - 0.85 * (i % 3), ev["title"][:22], fontsize=5.5, color=MUTED, ha="left", va="top",
                bbox=dict(facecolor="white", edgecolor="none", pad=0.6, alpha=0.8))
    ax.set_ylim(0, 10)
    ax.set_yticks(range(0, 11, 2))
    _style(ax, start, end)
    ax.legend(loc="lower left", frameon=False, ncol=3, fontsize=6.5)
    return _png(fig)


def category_charts(series: dict, start: date, end: date) -> bytes:
    cats = series["categories"]
    rows = (len(cats) + 3) // 4
    fig, axes = plt.subplots(rows, 4, figsize=(7.2, 1.25 * rows), sharex=True)
    axes = axes.flatten()
    for ax, cat in zip(axes, cats):
        dates = [date.fromisoformat(x) for x in cat["dates"]]
        ax.scatter(dates, cat["values"], s=4, color=POINT, alpha=0.4, linewidths=0, zorder=3)
        xs, ys = [], []
        for dt, val in zip(dates, cat["smoothed"]):
            if val is None:
                if xs:
                    ax.plot(xs, ys, color=SERIES, linewidth=1.1, zorder=4)
                xs, ys = [], []
            else:
                xs.append(dt); ys.append(val)
        if xs:
            ax.plot(xs, ys, color=SERIES, linewidth=1.1, zorder=4)
        if cat.get("baseline") is not None:
            ax.axhline(cat["baseline"], color=FAINT, linewidth=0.8, linestyle=(0, (4, 3)))
        ax.set_title(cat["label"] if len(cat["label"]) < 16 else "Good days > bad")
        ax.set_ylim(0, 10); ax.set_yticks([0, 5, 10])
        _style(ax, start, end, max_ticks=3)
        ax.tick_params(axis="x", labelsize=6, labelbottom=True)
    for ax in axes[len(cats):]:
        ax.axis("off")
    fig.tight_layout(h_pad=0.8, w_pad=1.2)
    return _png(fig)


def days_strip(entries_by_date: dict, start: date, end: date) -> bytes:
    """One small square per day: good / mixed / bad / not logged."""
    days = (end - start).days + 1
    fig, ax = plt.subplots(figsize=(7.2, 0.4))
    colors = {"good": GOOD, "mixed": MIXED, "bad": BAD}
    for i in range(days):
        day = start + timedelta(days=i)
        status = entries_by_date.get(day)
        ax.add_patch(plt.Rectangle((i, 0), 0.85, 1, color=colors.get(status, "#eef2f9"), linewidth=0))
    ax.set_xlim(0, days); ax.set_ylim(0, 1); ax.axis("off")
    return _png(fig)

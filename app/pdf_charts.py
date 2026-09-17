"""Chart images for the PDF, drawn with matplotlib.

These mirror the on-screen charts: one hue for the data, a dashed gray
threshold line, recessive grid, no dual axes.
"""
import io
from datetime import date

import matplotlib

matplotlib.use("Agg")  # no display needed
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from .scoring import ACCEPTABLE_TOTAL, MAX_TOTAL  # noqa: E402

SERIES = "#3b6cf5"
THRESHOLD = "#8a8a8a"
GRID = "#e0ddd5"
INK = "#2b2b2b"
MUTED = "#6b6b6b"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8,
    "axes.edgecolor": GRID,
    "axes.labelcolor": MUTED,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.titlecolor": INK,
    "axes.titlesize": 9,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
})


def _style(ax, dates: list[date], max_ticks: int = 8):
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    span = (max(dates) - min(dates)).days if len(dates) > 1 else 1
    if span > 180:
        fmt = mdates.DateFormatter("%b")
    else:
        fmt = FuncFormatter(lambda x, _: f"{mdates.num2date(x):%b} {mdates.num2date(x).day}")
    locator = mdates.AutoDateLocator(minticks=2, maxticks=max_ticks)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(fmt)


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def total_chart(dates: list[date], totals: list[int]) -> bytes:
    fig, ax = plt.subplots(figsize=(7.2, 2.4))
    ax.plot(dates, totals, color=SERIES, linewidth=1.6,
            marker="o", markersize=2.5 if len(dates) <= 60 else 0, label="Total score")
    ax.axhline(ACCEPTABLE_TOTAL, color=THRESHOLD, linewidth=1, linestyle=(0, (5, 4)),
               label=f"Threshold ({ACCEPTABLE_TOTAL})")
    ax.set_ylim(0, MAX_TOTAL)
    ax.set_yticks(range(0, MAX_TOTAL + 1, 10))
    _style(ax, dates)
    ax.legend(loc="lower left", frameon=False, ncol=2, fontsize=7)
    return _png(fig)


def category_charts(dates: list[date], categories: list[dict]) -> bytes:
    rows = (len(categories) + 2) // 3
    fig, axes = plt.subplots(rows, 3, figsize=(7.2, 1.35 * rows), sharex=True)
    axes = axes.flatten()
    for ax, cat in zip(axes, categories):
        ax.plot(dates, cat["values"], color=SERIES, linewidth=1.2,
                marker="o", markersize=1.5 if len(dates) <= 40 else 0)
        ax.set_title(cat["label"])
        ax.set_ylim(0, 10)
        ax.set_yticks([0, 5, 10])
        _style(ax, dates, max_ticks=3)
        ax.tick_params(axis="x", labelsize=6.5, labelbottom=True)
    for ax in axes[len(categories):]:
        ax.axis("off")
    fig.tight_layout(h_pad=1.0, w_pad=1.5)
    return _png(fig)


def weight_chart(dates: list[date], weights: list[float | None], unit: str) -> bytes:
    pairs = [(d, w) for d, w in zip(dates, weights) if w is not None]
    fig, ax = plt.subplots(figsize=(7.2, 1.8))
    ax.plot([d for d, _ in pairs], [w for _, w in pairs], color=SERIES, linewidth=1.6,
            marker="o", markersize=2.5)
    values = [w for _, w in pairs]
    pad = max((max(values) - min(values)) * 0.25, 0.5)
    ax.set_ylim(max(0, min(values) - pad), max(values) + pad)
    ax.set_ylabel(unit)
    _style(ax, dates)
    return _png(fig)

"""Draw Kyiv air raid alerts as a calendar: one cell per day, shaded by hours under alert.

Usage:
    uv run make_chart_calendar.py daily_alerts.csv kyiv_air_alerts_calendar.png
"""

import sys
import textwrap

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from make_chart import EVENTS, GRID, LEFT, MUTED, PAGE_BG, PERIODS, TEXT, period_index, short_date

HOURS_CAP = 20
HOURS_RAMP = LinearSegmentedColormap.from_list("ink", ["#F1EEE8", "#B9B0A4", "#5E554C", "#1E1A17"])
NORM = Normalize(vmin=0, vmax=HOURS_CAP)
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
BADGE = {"boxstyle": "circle,pad=0.25", "facecolor": TEXT, "edgecolor": "none"}
STRIPE = 0.07  # width of the period stripe, as a fraction of a cell
FOOTER = (
    "Data: official KMDA (Kyiv City State Administration) Telegram channel. An alert runs from "
    '"ATTENTION! declared in Kyiv..." to "All clear";\nits full duration counts toward the '
    "Kyiv-time day it started. From Sep 6, yellow (drone) and red (missile) alerts are both "
    "counted;\na change of threat level is not a new alert. Data through {last}. "
    "Periods and events: KMDA, Kyiv Independent, Kyiv Post, AP, Reuters."
)


def is_dark(hours: float) -> bool:
    red, green, blue, _ = HOURS_RAMP(NORM(min(hours, HOURS_CAP)))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue < 0.58


def draw_day(ax: Axes, day: pd.Timestamp, row: int, *, count: int, hours: float, bar: str) -> None:
    col = day.weekday()
    ax.add_patch(Rectangle((col + 0.03, row + 0.04), 0.94, 0.92, color=HOURS_RAMP(NORM(hours)),
                           lw=0, zorder=2))  # fmt: skip
    ax.add_patch(Rectangle((col + 0.03, row + 0.04), STRIPE, 0.92, color=bar, lw=0, zorder=3))
    ink = "#FFFFFF" if is_dark(hours) else TEXT
    soft = "#EDE8E1" if is_dark(hours) else "#4E4740"
    date_label = short_date(day) if day.day == 1 else str(day.day)
    ax.text(col + 0.14, row + 0.2, date_label, fontsize=8.5, color=soft, va="center", zorder=4)
    ax.text(col + 0.14, row + 0.62, str(count), fontsize=15, fontweight="bold", va="center",
            color=ink if count else soft, zorder=4)  # fmt: skip
    if hours > 0:
        hours_label = "<0.1 h" if hours < 0.05 else f"{hours:.1f} h"
        ax.text(col + 0.93, row + 0.66, hours_label, fontsize=8.5, ha="right", va="center",
                color=soft, zorder=4)  # fmt: skip


def draw_calendar(ax: Axes, daily: pd.DataFrame) -> None:
    days = pd.DatetimeIndex(daily.index)
    first_monday = days[0] - pd.Timedelta(days=days[0].weekday())
    periods = period_index(days)
    rows = zip(days, daily["count"], daily["hours"], periods, strict=True)
    for day, count, hours, period in rows:
        row = (day - first_monday).days // 7
        draw_day(ax, day, row, count=int(count), hours=float(hours), bar=PERIODS[period].bar)
    for number, event in enumerate(EVENTS, start=1):
        day = pd.Timestamp(event.day)
        row = (day - first_monday).days // 7
        ax.text(day.weekday() + 0.9, row + 0.2, str(number), ha="center", va="center", zorder=5,
                fontsize=9, fontweight="bold", color=PAGE_BG,
                bbox=BADGE)  # fmt: skip
    weeks = (days[-1] - first_monday).days // 7 + 1
    ax.set_xlim(0, 7)
    ax.set_ylim(weeks, 0)
    ax.set_xticks(np.arange(7) + 0.5)
    ax.set_xticklabels(WEEKDAYS)
    ax.xaxis.tick_top()
    ax.set_yticks([])
    ax.tick_params(length=0, labelsize=11, colors=MUTED)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_facecolor(PAGE_BG)


def draw_key(fig: Figure, daily: pd.DataFrame) -> None:
    fig.text(0.655, 0.835, "How to read a day", fontsize=13, fontweight="bold", color=TEXT)
    fig.text(0.655, 0.81, "Big number: alerts that day\nShade and small figure: hours under alert",
             fontsize=10.5, color=TEXT, va="top", linespacing=1.5)  # fmt: skip
    bar_ax = fig.add_axes((0.655, 0.735, 0.29, 0.018))
    bar_ax.imshow(np.linspace(0, 1, 256)[None, :], aspect="auto", cmap=HOURS_RAMP)
    bar_ax.set_yticks([])
    bar_ax.set_xticks(np.linspace(0, 255, 5))
    bar_ax.set_xticklabels(["0 h", "5", "10", "15", "20+ h"])
    bar_ax.tick_params(length=0, labelsize=9.5, colors=MUTED)
    for spine in bar_ax.spines.values():
        spine.set_visible(False)

    fig.text(0.655, 0.665, "Periods (stripe on each day)", fontsize=13, fontweight="bold",
             color=TEXT)  # fmt: skip
    days = pd.DatetimeIndex(daily.index)
    periods = period_index(days)
    y = 0.64
    for i in pd.unique(periods):
        span = daily[periods == i]
        first, last = pd.DatetimeIndex(span.index)[[0, -1]]
        name = textwrap.fill(PERIODS[i].name, 40)
        lines = name.count("\n") + 1
        fig.add_artist(Rectangle((0.655, y - 0.012 - 0.018 * lines), 0.006, 0.018 * lines + 0.03,
                                 color=PERIODS[i].bar, transform=fig.transFigure))  # fmt: skip
        detail = (
            f"{short_date(first)} – {short_date(last)}\n"
            f"{span['count'].mean():.1f} alerts, {span['hours'].mean():.1f} h a day"
        )
        fig.text(0.67, y, name, fontsize=10.5, fontweight="bold", color=TEXT, va="top")
        fig.text(0.67, y - 0.0185 * lines, detail, fontsize=10, color=MUTED, va="top",
                 linespacing=1.4)  # fmt: skip
        y -= 0.0185 * lines + 0.062


def plot(daily: pd.DataFrame, out_png: str) -> None:
    days = pd.DatetimeIndex(daily.index)
    fig = plt.figure(figsize=(12, 11), dpi=150)
    fig.patch.set_facecolor(PAGE_BG)
    cal = fig.add_axes((LEFT, 0.215, 0.56, 0.635))
    draw_calendar(cal, daily)
    draw_key(fig, daily)

    first, last = days[0], days[-1]
    title = f"Air raid alerts in Kyiv by day, {short_date(first)} – {short_date(last)}, {last.year}"
    fig.text(LEFT, 0.948, title, fontsize=22, va="baseline", fontweight="bold", color=TEXT)
    fig.text(LEFT, 0.912, "Each square is one day, read like a calendar, week by week.",
             fontsize=12, color=MUTED, va="baseline")  # fmt: skip
    fig.add_artist(plt.Line2D([LEFT, 0.95], [0.2, 0.2], color=GRID, lw=1))
    events = "\n".join(f"{n}  {e.note}" for n, e in enumerate(EVENTS, start=1))
    fig.text(LEFT, 0.188, events, fontsize=10, color=TEXT, linespacing=1.6, va="top")
    footer = FOOTER.format(last=f"{short_date(last)}, {last.year}")
    fig.text(LEFT, 0.014, footer, fontsize=10, color=MUTED, linespacing=1.6)
    fig.savefig(out_png, facecolor=PAGE_BG)
    print(f"Saved {out_png}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    plot(pd.read_csv(sys.argv[1], index_col="date", parse_dates=True), sys.argv[2])

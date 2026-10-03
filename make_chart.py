"""Draw "Air raid alerts in Kyiv by day" from daily_alerts.csv, coloured by war period.

Usage:
    uv run make_chart.py daily_alerts.csv kyiv_air_alerts.png
"""

import logging
import sys
from collections.abc import Callable
from typing import NamedTuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Patch

PAGE_BG = "#FAF8F4"
GRID = "#E3E1DC"
TEXT = "#1A1A1A"
MUTED = "#666666"


class Period(NamedTuple):
    """A span of days drawn in one colour; it runs until the next period's start."""

    start: str
    name: str
    bar: str
    tint: str
    line: str
    label_dx: float  # days from the period's first bar to its "avg" label at the panel top


class Event(NamedTuple):
    """A single day marked with a numbered line and explained in the footer."""

    day: str
    note: str


# Sources (fact-checked Oct 3, 2026): KMDA channel posts; Kyiv Post, RBC-Ukraine, Kyiv Independent
# (Aug 27 shift to near-continuous jet-drone waves); TASS, AP, ACLED, OSW (Sep 5-7 mutual pause on
# capitals); Kyiv Independent, AP, Ukrainska Pravda (Sep 20 - Oct 3 drone attacks with ballistic
# strikes); State Emergency Service final tolls via UNN (Jul 2: 31) and NV, Kyiv1 (Aug 20: 16).
PERIODS = [
    Period("2026-07-01", "Periodic mass strikes", "#C4C1B8", "#F3F2EE", "#555555", 1.5),
    Period("2026-08-27", "Near-continuous jet-drone waves on Kyiv",
           "#E0452B", "#F9EFEA", "#E0452B", 0.4),
    Period("2026-09-06", "Envoy pause, then fewer alert hours",
           "#2B7BD6", "#EEF2F6", "#2B7BD6", 1.0),
    Period("2026-09-20", "Round-the-clock jet-drone attacks, with ballistic strikes",
           "#9E1B32", "#F6EAEC", "#9E1B32", 1.0),
]  # fmt: skip
EVENTS = [
    Event("2026-07-01", "Night of Jul 1-2: deadliest attack on Kyiv this year, 31 killed"),
    Event("2026-08-19", "Night of Aug 19-20: mass missile and drone attack, 16 killed in Kyiv"),
    Event("2026-08-22", "Aug 22: Our group arrives in Kyiv"),
    Event("2026-08-27", "Aug 27: Our group's last day in Kyiv"),
    Event(
        "2026-09-06",
        "Sep 6: mutual pause on strikes against capitals for US envoys (ended Sep 7); "
        "Kyiv adopts graded alerts",
    ),
]
FOOTER = (
    "Data: official KMDA (Kyiv City State Administration) Telegram channel. An alert runs from "
    '"ATTENTION! declared in Kyiv..." to "All clear";\nits full duration counts toward the '
    "Kyiv-time day it started. From Sep 6, yellow (drone) and red (missile) alerts are both "
    "counted;\na change of threat level is not a new alert. Data through {last}. "
    "Periods and events: KMDA, Kyiv Independent, Kyiv Post, AP, Reuters."
)
LEFT = 0.05

logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
plt.rcParams["font.family"] = ["IBM Plex Sans", "DejaVu Sans", "sans-serif"]


def period_index(days: pd.DatetimeIndex) -> np.ndarray:
    """Position in PERIODS of the period each day falls in."""
    starts = pd.DatetimeIndex([p.start for p in PERIODS])
    if days[0] < starts[0]:
        raise ValueError(f"{days[0]:%Y-%m-%d} is before the first period; extend PERIODS")
    return starts.searchsorted(days, side="right") - 1


def draw_period(ax: Axes, x: np.ndarray, values: pd.Series, period: Period, fmt) -> None:
    lo, hi = x[0] - 0.5, x[-1] + 0.5
    ax.axvspan(lo, hi, color=period.tint, zorder=0, lw=0)
    ax.bar(x, values.to_numpy(), width=0.8, color=period.bar, zorder=3)
    avg = values.mean()
    ax.hlines(avg, lo, hi, colors=period.line, linestyles=(0, (4, 3)), lw=2, zorder=4)
    ax.text(
        x[0] - 0.5 + period.label_dx, 0.97, fmt(avg), transform=ax.get_xaxis_transform(),
        va="top", zorder=5, fontdict={"color": period.line, "fontsize": 11, "fontweight": "bold"},
    )  # fmt: skip


def draw_events(ax: Axes, days: pd.DatetimeIndex, numbered: bool) -> None:
    for number, event in enumerate(EVENTS, start=1):
        x = days.get_loc(pd.Timestamp(event.day))
        ax.axvline(x, color=TEXT, lw=1, ls=(0, (1, 2)), zorder=4.5)
        if numbered:
            ax.text(
                x, 1.01, str(number), transform=ax.get_xaxis_transform(), ha="center",
                va="bottom", fontsize=10, fontweight="bold", color=PAGE_BG,
                bbox={"boxstyle": "circle,pad=0.25", "facecolor": TEXT, "edgecolor": "none"},
            )  # fmt: skip


def draw_panel(ax: Axes, series: pd.Series, title: str, fmt: Callable[[float], str]) -> None:
    days = pd.DatetimeIndex(series.index)
    x = np.arange(len(series))
    periods = period_index(days)
    for i in pd.unique(periods):
        mask = periods == i
        draw_period(ax, x[mask], series[mask], PERIODS[i], fmt)

    ax.annotate(
        title, xy=(LEFT, 1), xycoords=("figure fraction", "axes fraction"),
        xytext=(0, 12.5), textcoords="offset points",
        fontsize=16, fontweight="bold", color=TEXT, va="baseline",
    )  # fmt: skip
    ax.set_facecolor(PAGE_BG)
    ax.grid(axis="y", color=GRID, lw=1, zorder=1)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0, labelsize=12, colors=MUTED)
    ax.set_xlim(-0.5, len(series) - 0.5)
    ticks = tick_days(days)
    ax.set_xticks([days.get_loc(t) for t in ticks])
    ax.set_xticklabels([short_date(t) for t in ticks])


def tick_days(days: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """The 1st and 15th of each month, then the last day, skipping ticks that would crowd it."""
    last = days[-1]
    ticks = [d for d in days if d.day in (1, 15) and (last - d).days > 5]
    return [*ticks, last]


def short_date(day: pd.Timestamp) -> str:
    return f"{day:%b} {day.day}"


def legend_handles(days: pd.DatetimeIndex) -> list[Patch]:
    periods = period_index(days)
    handles = []
    for i in pd.unique(periods):
        span = days[periods == i]
        label = f"{PERIODS[i].name} ({short_date(span[0])} – {short_date(span[-1])})"
        handles.append(Patch(color=PERIODS[i].bar, label=label))
    return handles


def draw_header_and_footer(fig: Figure, days: pd.DatetimeIndex) -> None:
    first, last = days[0], days[-1]
    title = f"Air raid alerts in Kyiv by day, {short_date(first)} – {short_date(last)}, {last.year}"
    fig.text(LEFT, 0.948, title, fontsize=22, va="baseline", fontweight="bold", color=TEXT)
    fig.legend(
        handles=legend_handles(days), loc="upper left", bbox_to_anchor=(LEFT - 0.008, 0.937),
        ncol=2, frameon=False, fontsize=11, handlelength=0.8, handleheight=0.8,
        handletextpad=0.5, columnspacing=2.2,
    )  # fmt: skip
    fig.add_artist(plt.Line2D([LEFT, 0.95], [0.2, 0.2], color=GRID, lw=1))
    events = "\n".join(f"{n}  {e.note}" for n, e in enumerate(EVENTS, start=1))
    fig.text(LEFT, 0.188, events, fontsize=10, color=TEXT, linespacing=1.6, va="top")
    footer = FOOTER.format(last=f"{short_date(last)}, {last.year}")
    fig.text(LEFT, 0.014, footer, fontsize=10, color=MUTED, linespacing=1.6)


def plot(daily: pd.DataFrame, out_png: str) -> None:
    days = pd.DatetimeIndex(daily.index)
    hours_top = max(20, 5 * int(np.ceil(daily["hours"].max() / 5)))
    count_top = max(12, 3 * int(np.ceil(daily["count"].max() / 3)))
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 11), dpi=150)
    fig.patch.set_facecolor(PAGE_BG)
    fig.subplots_adjust(top=0.835, bottom=0.26, left=0.07, right=0.947, hspace=0.432)

    draw_panel(ax1, daily["hours"], "Hours under alert", lambda v: f"avg {v:.1f} h")
    ax1.set_ylim(0, hours_top * 1.025)
    ax1.set_yticks(range(0, hours_top + 1, 5))
    draw_panel(ax2, daily["count"], "Number of alerts", lambda v: f"avg {v:.1f}/day")
    ax2.set_ylim(0, max(count_top * 1.04, daily["count"].max() * 1.1))
    ax2.set_yticks(range(0, count_top + 1, 3))
    draw_events(ax1, days, numbered=True)
    draw_events(ax2, days, numbered=False)

    draw_header_and_footer(fig, days)
    fig.savefig(out_png, facecolor=PAGE_BG)
    print(f"Saved {out_png}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    plot(pd.read_csv(sys.argv[1], index_col="date", parse_dates=True), sys.argv[2])

"""Draw Kyiv air raid alerts as a 24-hour clock view: one column per day, real alert times.

Usage:
    uv run make_chart_clock.py result.json daily_alerts.csv kyiv_air_alerts_clock.png
"""

import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.patches import Patch

from build_daily import alert_events, load_window, pair_alerts
from make_chart import (
    EVENTS,
    GRID,
    LEFT,
    MUTED,
    PAGE_BG,
    PERIODS,
    TEXT,
    draw_events,
    period_index,
    short_date,
    tick_days,
)

MIN_BLOCK_HOURS = 0.15  # 9 minutes, so a one-minute alert still shows as a block
FOOTER = (
    "Data: official KMDA (Kyiv City State Administration) Telegram channel. Each block is one "
    'alert, from "ATTENTION! declared in Kyiv..." to "All clear", drawn at\nits real Kyiv time; '
    "an alert that crosses midnight continues at the top of the next column. Alerts shorter than "
    "9 minutes are drawn 9 minutes tall.\nAlerts per day and period averages assign each alert to "
    "the day it started. From Sep 6, yellow (drone) and red (missile) alerts are both counted; a "
    "change of\nthreat level is not a new alert. Data through {last}. "
    "Periods and events: KMDA, Kyiv Independent, Kyiv Post, AP, Reuters."
)


def day_segments(alerts: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    """Split each alert at midnight into (day position, start hour, end hour) pieces."""
    rows = []
    for start, end in alerts[["start", "end"]].itertuples(index=False):
        cursor = start
        while cursor < end:
            day = cursor.normalize()
            piece_end = min(end, day + pd.Timedelta(days=1))
            if day in days:
                top = (cursor - day).total_seconds() / 3600
                bottom = (piece_end - day).total_seconds() / 3600
                rows.append((days.get_loc(day), top, max(bottom, top + MIN_BLOCK_HOURS)))
            cursor = piece_end
    return pd.DataFrame(rows, columns=["x", "top", "bottom"])


def draw_clock(ax: Axes, segments: pd.DataFrame, days: pd.DatetimeIndex) -> None:
    periods = period_index(days)
    for i in pd.unique(periods):
        span = np.flatnonzero(periods == i)
        ax.axvspan(span[0] - 0.5, span[-1] + 0.5, color=PERIODS[i].tint, zorder=0, lw=0)
    colors = [PERIODS[periods[x]].bar for x in segments["x"]]
    ax.bar(
        segments["x"], segments["bottom"] - segments["top"], bottom=segments["top"],
        width=0.78, color=colors, zorder=3,
    )  # fmt: skip
    ax.set_ylim(24, 0)
    ax.set_yticks(range(0, 25, 6))
    ax.set_yticklabels([f"{h:02d}:00" for h in range(0, 25, 6)])
    ax.set_xlim(-0.5, len(days) - 0.5)
    ax.set_xticks([])
    ax.grid(axis="y", color=GRID, lw=1, zorder=1)
    ax.set_axisbelow(True)
    style_axes(ax)
    ax.annotate(
        "When Kyiv was under alert, by time of day", xy=(LEFT, 1),
        xycoords=("figure fraction", "axes fraction"), xytext=(0, 26), textcoords="offset points",
        fontsize=16, fontweight="bold", color=TEXT, va="baseline",
    )  # fmt: skip


def draw_count_row(ax: Axes, daily: pd.DataFrame) -> None:
    days = pd.DatetimeIndex(daily.index)
    periods = period_index(days)
    colors = [PERIODS[i].bar for i in periods]
    ax.bar(np.arange(len(days)), daily["count"], width=0.78, color=colors, zorder=3)
    most = int(daily["count"].max())
    ax.set_ylim(0, most * 1.08)
    ax.set_yticks(range(0, most + 1, 6))
    ax.grid(axis="y", color=GRID, lw=1, zorder=1)
    ax.set_xlim(-0.5, len(days) - 0.5)
    ticks = tick_days(days)
    ax.set_xticks([days.get_loc(t) for t in ticks])
    ax.set_xticklabels([short_date(t) for t in ticks])
    style_axes(ax)
    ax.annotate(
        "Alerts per day", xy=(LEFT, 1), xycoords=("figure fraction", "axes fraction"),
        xytext=(0, 8), textcoords="offset points", fontsize=12, fontweight="bold", color=TEXT,
        va="baseline",
    )  # fmt: skip


def style_axes(ax: Axes) -> None:
    ax.set_facecolor(PAGE_BG)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0, labelsize=12, colors=MUTED)


def legend_handles(daily: pd.DataFrame) -> list[Patch]:
    days = pd.DatetimeIndex(daily.index)
    periods = period_index(days)
    handles = []
    for i in pd.unique(periods):
        span = daily[periods == i]
        first, last = pd.DatetimeIndex(span.index)[[0, -1]]
        label = (
            f"{PERIODS[i].name} ({short_date(first)} – {short_date(last)}):  "
            f"{span['count'].mean():.1f} alerts, {span['hours'].mean():.1f} h a day"
        )
        handles.append(Patch(color=PERIODS[i].bar, label=label))
    return handles


def plot(alerts: pd.DataFrame, daily: pd.DataFrame, out_png: str) -> None:
    days = pd.DatetimeIndex(daily.index)
    fig = plt.figure(figsize=(12, 11), dpi=150)
    fig.patch.set_facecolor(PAGE_BG)
    clock = fig.add_axes((0.07, 0.385, 0.877, 0.4))
    counts = fig.add_axes((0.07, 0.258, 0.877, 0.075))
    draw_clock(clock, day_segments(alerts, days), days)
    draw_events(clock, days, numbered=True)
    draw_events(counts, days, numbered=False)
    draw_count_row(counts, daily)

    first, last = days[0], days[-1]
    title = f"Air raid alerts in Kyiv by day, {short_date(first)} – {short_date(last)}, {last.year}"
    fig.text(LEFT, 0.948, title, fontsize=22, va="baseline", fontweight="bold", color=TEXT)
    fig.legend(
        handles=legend_handles(daily), loc="upper left", bbox_to_anchor=(LEFT - 0.008, 0.932),
        ncol=1, frameon=False, fontsize=11.5, handlelength=0.8, handleheight=0.8,
        handletextpad=0.5, labelspacing=0.45,
    )  # fmt: skip
    fig.add_artist(plt.Line2D([LEFT, 0.95], [0.215, 0.215], color=GRID, lw=1))
    events = "\n".join(f"{n}  {e.note}" for n, e in enumerate(EVENTS, start=1))
    fig.text(LEFT, 0.203, events, fontsize=10, color=TEXT, linespacing=1.6, va="top")
    footer = FOOTER.format(last=f"{short_date(last)}, {last.year}")
    fig.text(LEFT, 0.012, footer, fontsize=9, color=MUTED, linespacing=1.6)
    fig.savefig(out_png, facecolor=PAGE_BG)
    print(f"Saved {out_png}")


def main(export_json: str, daily_csv: str, out_png: str) -> None:
    alerts, _, _ = pair_alerts(alert_events(load_window(export_json)))
    daily = pd.read_csv(daily_csv, index_col="date", parse_dates=True)
    plot(alerts, daily, out_png)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3])

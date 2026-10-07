"""Draw the share of time under alert by time of day, for each period, as a print-ready PNG.

Usage:
    uv run make_chart_timeofday.py result.json kyiv_air_alerts_timeofday.png

Each alert is split minute by minute across the time-of-day bands it ran through (Kyiv time)
and assigned to the period of the day it started. The top bar is each band's share of the
24-hour clock, for reference.
"""

import sys
from datetime import date, timedelta
from typing import NamedTuple

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.axes import Axes

from build_daily import END_DATE, alert_events, load_window, pair_alerts
from make_chart import PERIODS

TEXT = "#1B2130"
MUTED = "#5A6376"
RULE = "#DCE0E8"


class Band(NamedTuple):
    """A time-of-day band covering the given clock hours."""

    name: str
    hours: tuple[int, ...]
    fill: str
    ink: str


BANDS = [
    Band("Night 23:00–07:00", (23, 0, 1, 2, 3, 4, 5, 6), "#2E3A4F", "#FFFFFF"),
    Band("Morning 07:00–09:00", (7, 8), "#97A4BA", TEXT),
    Band("Working hours 09:00–18:00", tuple(range(9, 18)), "#C6CEDB", TEXT),
    Band("Evening 18:00–23:00", tuple(range(18, 23)), "#5F6E88", "#FFFFFF"),
]
BAND_OF_HOUR = {hour: band.name for band in BANDS for hour in band.hours}


class Row(NamedTuple):
    """One bar: alerts that started from `first` to `last` (inclusive)."""

    name: str
    first: date
    last: date


def short_range(first: date, last: date) -> str:
    if first.month == last.month:
        return f"{first:%b} {first.day}–{last.day}"
    return f"{first:%b} {first.day} – {last:%b} {last.day}"


def period_rows() -> list[Row]:
    """Before the first phase, all phases together, then each phase, using make_chart.PERIODS."""
    starts = [date.fromisoformat(p.start) for p in PERIODS]
    ends = [s - timedelta(days=1) for s in starts[1:]] + [date.fromisoformat(END_DATE)]
    since = starts[1]
    rows = [
        Row(f"Before {since:%b} {since.day}", starts[0], ends[0]),
        Row(f"Since {since:%b} {since.day}", since, ends[-1]),
    ]
    for i, (first, last) in enumerate(zip(starts[1:], ends[1:], strict=True), start=1):
        rows.append(Row(f"Phase {i}", first, last))
    return rows


def band_minutes(alerts: pd.DataFrame) -> pd.DataFrame:
    """Minutes under alert per band, one row per alert, indexed like `alerts`."""
    out = []
    for start, end in alerts[["start", "end"]].itertuples(index=False):
        minutes = pd.date_range(start.floor("min"), end, freq="min", inclusive="left")
        out.append(pd.Series(minutes).dt.hour.map(BAND_OF_HOUR).value_counts())
    table = pd.DataFrame(out, index=alerts.index).fillna(0)
    return table.reindex(columns=[b.name for b in BANDS], fill_value=0)


def shares(alerts: pd.DataFrame, rows: list[Row]) -> pd.DataFrame:
    """Percent of time under alert per band; first row is the 24-hour clock."""
    minutes = band_minutes(alerts)
    day = alerts["start"].dt.normalize()
    table = {"Share of the clock": {b.name: len(b.hours) / 24 * 100 for b in BANDS}}
    for row in rows:
        in_row = minutes[(day >= f"{row.first}") & (day <= f"{row.last}")].sum()
        table[row.name] = in_row / in_row.sum() * 100
    return pd.DataFrame(table).T


def draw_bars(ax: Axes, table: pd.DataFrame, subtitles: list[str]) -> None:
    for y, (name, pcts) in enumerate(table.iterrows()):
        is_clock = y == 0
        left = 0.0
        for band in BANDS:
            pct = pcts[band.name]
            ax.barh(y, pct, left=left, height=0.68, color=band.fill, alpha=0.45 if is_clock else 1,
                    edgecolor="white", linewidth=1.5)  # fmt: skip
            if pct >= 5:
                ax.text(left + pct / 2, y, f"{pct:.0f}%", ha="center", va="center", fontsize=10,
                        color=TEXT if is_clock else band.ink, fontweight="medium")  # fmt: skip
            left += pct
        ax.text(-1.5, y - 0.1, str(name), ha="right", va="center", fontsize=11, color=TEXT,
                fontweight="bold" if y in (1, 2) else "normal")  # fmt: skip
        ax.text(-1.5, y + 0.22, subtitles[y], ha="right", va="center", fontsize=9, color=MUTED)
    ax.axhline(0.5, color=RULE, linewidth=1)
    ax.set_xlim(0, 100)
    ax.set_ylim(len(table) - 0.5, -0.5)
    ax.axis("off")


def plot(table: pd.DataFrame, subtitles: list[str], out_png: str) -> None:
    plt.rcParams["font.family"] = ["IBM Plex Sans", "DejaVu Sans", "sans-serif"]
    fig = plt.figure(figsize=(10, 5.2), dpi=300)
    ax = fig.add_axes((0.2, 0.17, 0.77, 0.66))
    draw_bars(ax, table, subtitles)
    fig.text(0.03, 0.93, "When Kyiv is under air raid alert", fontsize=16, fontweight="bold",
             color=TEXT, va="baseline")  # fmt: skip
    fig.text(0.03, 0.875, "Share of time under alert by time of day (Kyiv time)", fontsize=11,
             color=MUTED, va="baseline")  # fmt: skip
    handles = [plt.Rectangle((0, 0), 1, 1, color=b.fill) for b in BANDS]
    fig.legend(handles, [b.name for b in BANDS], loc="lower left", bbox_to_anchor=(0.2, 0.07),
               ncol=4, frameon=False, fontsize=9.5, handlelength=0.9, handleheight=0.9,
               columnspacing=1.4)  # fmt: skip
    fig.text(0.03, 0.025, "Data: official KMDA (Kyiv City State Administration) Telegram "
             "channel. Each alert is split by minute across the bands it ran through and\n"
             "assigned to the period of the day it started. The top bar shows each band's share "
             "of the 24-hour day.", fontsize=8, color=MUTED, linespacing=1.5)  # fmt: skip
    fig.savefig(out_png, facecolor="white")


def main(export_json: str, out_png: str) -> None:
    alerts, _, _ = pair_alerts(alert_events(load_window(export_json)))
    rows = period_rows()
    table = shares(alerts, rows)
    print(table.round(1).to_string())
    subtitles = ["reference"] + [short_range(r.first, r.last) for r in rows]
    plot(table, subtitles, out_png)
    print(f"\nWrote {out_png}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])

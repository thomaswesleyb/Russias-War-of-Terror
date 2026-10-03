"""Turn a Telegram Desktop JSON export into a daily table of Kyiv air-raid alerts.

Usage:
    uv run build_daily.py result.json daily_alerts.csv

Reads the channel's result.json, prints the checkpoint figures (rule matches, pairing
skips, extreme alerts, monthly means, Aug 27 - Sep 28 averages) and writes one row per
day with `count` and `hours`.
"""

import json
import sys

import pandas as pd

KYIV = "Europe/Kyiv"

START_DATE = "2026-07-01"
END_DATE = "2026-10-03"
# Alerts are assigned to the Kyiv day they start, so stop at midnight after END_DATE.
CUTOFF = pd.Timestamp(END_DATE) + pd.Timedelta(days=1)

END_PATTERN = "відбій повітряної тривоги"  # "All clear for the air alert"
# "ATTENTION! ... declared in Kyiv": covers "air alert" and, from Sep 6, the
# differentiated "drone danger" / "missile threat" / "new threat" levels.
START_PATTERN = "увага! у києві оголошена"


def load_messages(export_json: str) -> pd.DataFrame:
    """Load channel posts with Kyiv-time timestamps from `date_unixtime`.

    The export's `date` field is the exporting machine's local time, so it is not used.
    """
    with open(export_json, encoding="utf-8") as f:
        export = json.load(f)
    rows = []
    for msg in export["messages"]:
        if msg["type"] != "message":
            continue
        if "date_unixtime" not in msg:
            raise ValueError(f"Message {msg['id']} has no date_unixtime; re-export as JSON")
        text = "".join(entity["text"] for entity in msg["text_entities"])
        rows.append((msg["id"], int(msg["date_unixtime"]), text))
    df = pd.DataFrame(rows, columns=["id", "unixtime", "text"])
    df["ts"] = (
        pd.to_datetime(df["unixtime"], unit="s", utc=True).dt.tz_convert(KYIV).dt.tz_localize(None)
    )
    return df


def classify(df: pd.DataFrame) -> pd.DataFrame:
    text = df["text"].str.lower()
    # All-clear is checked first so that it wins if a post ever matches both.
    is_end = text.str.contains(END_PATTERN, regex=False)
    is_start = ~is_end & text.str.contains(START_PATTERN, regex=False)
    df["kind"] = None
    df.loc[is_end, "kind"] = "end"
    df.loc[is_start, "kind"] = "start"
    return df


def print_rule_matches(window: pd.DataFrame) -> None:
    counts = window["kind"].value_counts()
    print(f"\nMessages {START_DATE} .. cutoff {CUTOFF}: {len(window)}")
    print(f"  start rule: {counts.get('start', 0)}")
    print(f"  end rule:   {counts.get('end', 0)}")
    print(f"  neither:    {window['kind'].isna().sum()}")


def pair_alerts(events: pd.DataFrame) -> tuple[pd.DataFrame, list[str], int]:
    """Pair starts with the next all-clear.

    Returns:
        Closed alerts, the text of each skipped start, and the number of skipped ends.
    """
    alerts, skipped_starts, skipped_ends = [], [], 0
    open_start = None
    for ts, kind, text in events[["ts", "kind", "text"]].itertuples(index=False):
        if kind == "start" and open_start is None:
            open_start = ts
        elif kind == "start":
            skipped_starts.append(text)
        elif open_start is not None:
            alerts.append((open_start, ts))
            open_start = None
        else:
            skipped_ends += 1
    if open_start is not None:
        print(f"Dropping alert with no all-clear, started {open_start}")
    df = pd.DataFrame(alerts, columns=["start", "end"])
    df["hours"] = (df["end"] - df["start"]).dt.total_seconds() / 3600
    return df, skipped_starts, skipped_ends


def print_pairing_report(
    alerts: pd.DataFrame, skipped_starts: list[str], skipped_ends: int
) -> None:
    print(f"\nAlerts: {len(alerts)}")
    print(f"Skipped starts (alert already open): {len(skipped_starts)}")
    headlines = pd.Series([s.split("!")[1].strip() for s in skipped_starts]).value_counts()
    for headline, n in headlines.items():
        print(f"  {n:3d} x {headline}")
    print(f"Skipped ends (no alert open): {skipped_ends}")
    by_length = alerts.sort_values("hours")
    print("Shortest:", fmt_alert(by_length.iloc[0]))
    print("Longest: ", fmt_alert(by_length.iloc[-1]))
    long = by_length[by_length["hours"] > 12]
    print(f"Alerts over 12 h: {len(long)}")
    for _, row in long.iterrows():
        print("  ", fmt_alert(row))


def fmt_alert(row: pd.Series) -> str:
    return f"{row['start']:%b %d %H:%M} -> {row['end']:%b %d %H:%M} ({row['hours']:.2f} h)"


def daily_table(alerts: pd.DataFrame) -> pd.DataFrame:
    day = alerts["start"].dt.normalize().rename("date")
    daily = alerts.groupby(day).agg(count=("hours", "size"), hours=("hours", "sum"))
    full = pd.date_range(START_DATE, END_DATE, freq="D", name="date")
    return daily.reindex(full, fill_value=0)


def print_averages(daily: pd.DataFrame) -> None:
    print("\nMonthly means over all days (zero days included):")
    months = daily.index.to_series().dt.month.to_numpy()
    print(daily.groupby(months).mean().round(2).to_string())
    late = daily.loc["2026-08-27":"2026-09-28"].mean()
    july = daily[months == 7].mean()
    print(
        f"\nAug 27 - Sep 28: {late['count']:.2f} alerts/day, {late['hours']:.2f} h/day "
        f"(July: {july['count']:.2f} alerts/day, {july['hours']:.2f} h/day; "
        f"{late['count'] / july['count']:.1f}x and {late['hours'] / july['hours']:.1f}x)"
    )


def load_window(export_json: str) -> pd.DataFrame:
    """Classified messages from START_DATE up to CUTOFF, in Kyiv time."""
    messages = classify(load_messages(export_json))
    return messages[(messages["ts"] >= START_DATE) & (messages["ts"] < CUTOFF)]


def alert_events(window: pd.DataFrame) -> pd.DataFrame:
    return window.dropna(subset=["kind"]).sort_values("ts", kind="stable")


def main(export_json: str, out_csv: str) -> None:
    window = load_window(export_json)
    print_rule_matches(window)
    alerts, skipped_starts, skipped_ends = pair_alerts(alert_events(window))
    print_pairing_report(alerts, skipped_starts, skipped_ends)
    daily = daily_table(alerts)
    daily.to_csv(out_csv, float_format="%.4f")
    print(f"\nWrote {out_csv} ({len(daily)} days)")
    print_averages(daily)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])

"""Commute Pulse pipeline.

Reads TfNSW Opal Tap Data (one pipe-delimited file per day) and writes the small
aggregated files the charts use.

Measure: tap-ons between 3pm and 7pm (people heading home) in each commercial
centre. Tap-offs are NOT used - they have unexplained breaks (e.g. CBD morning
tap-offs drop ~85% from Oct 2023 to Jun 2024) while tap-ons stay consistent.

Run:  python pipeline.py            (reads raw/*.txt, or opal_all.txt if raw/ is missing)
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent
OUT = ROOT / "out"

EVENING = range(15, 19)                      # 3:00pm - 6:59pm
BASELINE = ("2020-01-06", "2020-03-06")      # pre-COVID: after New Year, before March decline
CENTRES = ["Sydney CBD", "North Sydney", "Parramatta", "Chatswood",
           "Macquarie Park", "Strathfield"]
# Periods TfNSW documents as likely to have discrepancies
KNOWN_BAD = [("2025-01-28", "2025-02-05"), ("2026-01-28", "2026-02-12")]
ANOMALY_THRESHOLD = 0.70                     # weekday < 70% of its rolling same-weekday median
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri"]


def load() -> pd.DataFrame:
    raw = sorted((ROOT / "raw").glob("Opal_Patronage_*.txt"))
    files = raw if raw else [ROOT / "opal_all.txt"]
    df = pd.concat((pd.read_csv(f, sep="|", dtype=str) for f in files), ignore_index=True)
    df = df.rename(columns={"trip_origin_date": "date", "mode_name": "mode",
                            "ti_region": "region", "tap_hour": "hour"})
    df["date"] = pd.to_datetime(df["date"])
    df["hour"] = df["hour"].astype(int)
    for col, new in [("Tap_Ons", "tap_ons"), ("Tap_Offs", "tap_offs")]:
        s = df[col]
        suppressed = s.str.startswith("<", na=False)
        val = pd.to_numeric(s.where(~suppressed), errors="coerce")
        # "<50" / "<100" -> half the threshold (affects <1% of evening volume outside Newcastle)
        val[suppressed] = pd.to_numeric(s[suppressed].str[1:]) / 2
        df[new] = val
    df = df[df["mode"] != "UNKNOWN"]
    return df.drop(columns=["Tap_Ons", "Tap_Offs"])


def daily_evening(df: pd.DataFrame) -> pd.DataFrame:
    d = (df[df["hour"].isin(EVENING) & df["region"].isin(CENTRES)]
         .groupby(["region", "date"], as_index=False)["tap_ons"].sum())
    d["dow"] = d["date"].dt.dayofweek
    d = d.sort_values(["region", "dow", "date"])
    d["ref"] = (d.groupby(["region", "dow"])["tap_ons"]
                 .transform(lambda s: s.rolling(9, center=True, min_periods=3).median()))
    d["flag"] = ""
    d.loc[(d["dow"] < 5) & (d["tap_ons"] < ANOMALY_THRESHOLD * d["ref"]), "flag"] = "low_day"
    for a, b in KNOWN_BAD:
        d.loc[d["date"].between(a, b), "flag"] = "tfnsw_discrepancy"
    return d.sort_values(["region", "date"]).reset_index(drop=True)


def weekday_gaps(d: pd.DataFrame, freq: str) -> pd.DataFrame:
    w = d[(d["dow"] < 5) & (d["flag"] == "")].copy()
    w["period"] = w["date"].dt.to_period(freq).dt.start_time
    p = (w.pivot_table(index=["region", "period"], columns="dow", values="tap_ons", aggfunc="mean")
          .rename(columns=dict(enumerate(DOW))))
    n = w.groupby(["region", "period"])["date"].nunique().rename("days")
    mid = p[["Tue", "Wed", "Thu"]].mean(axis=1)
    p["mon_vs_midweek"] = p["Mon"] / mid
    p["fri_vs_midweek"] = p["Fri"] / mid
    return p.join(n).reset_index().round({c: 0 for c in DOW} | {"mon_vs_midweek": 3, "fri_vs_midweek": 3})


def baseline(d: pd.DataFrame) -> pd.DataFrame:
    w = d[(d["dow"] < 5) & (d["flag"] == "") & d["date"].between(*BASELINE)]
    p = w.pivot_table(index="region", columns="dow", values="tap_ons", aggfunc="mean").rename(columns=dict(enumerate(DOW)))
    mid = p[["Tue", "Wed", "Thu"]].mean(axis=1)
    p["mon_vs_midweek"] = p["Mon"] / mid
    p["fri_vs_midweek"] = p["Fri"] / mid
    return p.reset_index().round(3)


def hourly_profile(df: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
    """Average CBD tap-ons by hour and weekday: pre-COVID baseline vs last 12 months."""
    good = flags.loc[(flags["region"] == "Sydney CBD") & (flags["flag"] == ""), "date"]
    cbd = df[(df["region"] == "Sydney CBD") & df["date"].isin(good) & (df["date"].dt.dayofweek < 5)]
    last = cbd["date"].max()
    windows = {"pre_covid": BASELINE, "last_12m": (last - pd.DateOffset(months=12), last)}
    rows = []
    for name, (a, b) in windows.items():
        x = cbd[cbd["date"].between(a, b)]
        h = x.groupby(["date", "hour"])["tap_ons"].sum().reset_index()
        h["dow"] = h["date"].dt.dayofweek.map(dict(enumerate(DOW)))
        rows.append(h.groupby(["dow", "hour"])["tap_ons"].mean().reset_index().assign(window=name))
    return pd.concat(rows).round(0)


def main():
    OUT.mkdir(exist_ok=True)
    df = load()
    d = daily_evening(df)
    d.drop(columns=["ref"]).to_csv(OUT / "daily_evening_tapons.csv", index=False)
    weekday_gaps(d, "M").to_csv(OUT / "weekday_gap_monthly.csv", index=False)
    weekday_gaps(d, "Q").to_csv(OUT / "weekday_gap_quarterly.csv", index=False)
    baseline(d).to_csv(OUT / "baseline_pre_covid.csv", index=False)
    hourly_profile(df, d).to_csv(OUT / "cbd_hourly_profile.csv", index=False)
    print(f"{df['date'].min():%Y-%m-%d} to {df['date'].max():%Y-%m-%d}, {len(df):,} rows")
    print(f"flagged days: {(d['flag'] != '').sum()} region-days")
    print(baseline(d).to_string(index=False))


if __name__ == "__main__":
    main()

# Commute Pulse

Is Sydney back in the office? Opal tap data by commercial centre, hour and day of week, Jan 2020 to now.

## Data
TfNSW Open Data Hub - [Opal Tap Data](https://opendata.transport.nsw.gov.au/dataset/opal-patronage) (CC BY). One file per day: tap-ons and tap-offs by mode, region and hour, rounded to the nearest 100.

Download into `raw/` (free account needed; requests must send the referrer header):

```bash
mkdir -p raw && d=20200101; end=$(date +%Y%m%d); while [ "$d" -le "$end" ]; do m="${d:0:4}-${d:4:2}"; curl -sf -H "Referer: https://opendata.transport.nsw.gov.au/" -o "raw/Opal_Patronage_$d.txt" "https://opendata-tpa.transport.nsw.gov.au/Opal_Patronage/$m/Opal_Patronage_$d.txt" || echo "missing $d"; d=$(date -j -v+1d -f %Y%m%d "$d" +%Y%m%d); done
```

## Run
```bash
pip install -r requirements.txt
python pipeline.py
```

## Method
- **Measure:** tap-ons 3pm-7pm (people leaving work) per commercial centre. Tap-offs are excluded because they have unexplained structural breaks (CBD morning tap-offs fall ~85% from Oct 2023 to Jun 2024 while tap-ons stay flat).
- **Friday gap:** Friday volume / average of Tue-Thu, same period. Ratios within a period cancel out most data-level changes.
- **Baseline:** 6 Jan - 6 Mar 2020 (pre-COVID, after the New Year lull).
- **Excluded days:** weekdays below 70% of the rolling 9-week median for that weekday (public holidays, lockdown starts, outages) and TfNSW's documented discrepancy windows.
- **Suppressed counts** (`<50`, `<100`) set to half the threshold; under 1% of evening volume outside Newcastle.
- **Caveat:** the CBD region is defined by named stations and postcode 2000. It's unclear whether Sydney Metro taps (Barangaroo, Gadigal, Martin Place metro) are included, so CBD levels vs 2020 may be understated.

## Outputs (`out/`)
| File | What |
|---|---|
| `daily_evening_tapons.csv` | Evening tap-ons per centre per day, with exclusion flag |
| `weekday_gap_monthly.csv` / `_quarterly.csv` | Mon-Fri averages and Mon/Fri vs midweek ratios |
| `baseline_pre_covid.csv` | Same ratios for the pre-COVID baseline |
| `cbd_hourly_profile.csv` | CBD tap-ons by hour and weekday, pre-COVID vs last 12 months |

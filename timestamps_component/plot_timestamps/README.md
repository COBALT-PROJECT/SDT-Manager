# CDF Plot Generator

For the current timestamp manager, use `plot_events.py` with its JSONL archive or
CSV export. It produces one CDF per category/operation and a `summary.csv` with
count, mean, median, standard deviation, minimum, maximum, and failure count.
Completed records of all outcomes are included. Nested operations overlap and
must not be added together as end-to-end durations.

```bash
python3 plot_events.py ../performance_events.jsonl --output plots
python3 plot_events.py ../performance.csv --category token_distribution --output plots
```

The instructions below describe historical spreadsheets and plots from the former
Watchtower-enabled implementation. Those old scripts still operate on those files.

Generates 3 empirical CDF plots from `timestamps_results.xlsx`, each with mean (μ), median, and standard deviation (σ).

## Requirements

- Python 3.7+
- pandas, numpy, matplotlib, openpyxl

## Setup

```bash
pip install pandas numpy matplotlib openpyxl
```

## Usage

1. Place `plot_cdfs.py` and `timestamps_results.xlsx` in the same folder.
2. Run:

```bash
python plot_cdfs.py
```

## Output

| File | Description |
|------|-------------|
| `cdf_total_instantiation.png` | Sum of instantiate sdt + ids-sdt + watchtower |
| `cdf_total_send_token.png` | Sum of send token sdt + ids-sdt + watchtower |
| `cdf_register_am.png` | Register with AM |

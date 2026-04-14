# CDF Plot Generator

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

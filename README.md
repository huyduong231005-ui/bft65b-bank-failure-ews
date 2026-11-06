# A Big-Data Pipeline for Bank Failure Early Warning (BFT65B Final Report)

Reproducible pipeline on public FDIC data (Call Reports 1984Q1–2026Q2, Failures, Institutions):
acquisition → typed Parquet lake → automated data-quality audit → point-in-time panel and label →
Polars feature pipeline (benchmarked against pandas, reproduced in PySpark) → time-ordered
early-warning models (scikit-learn + Spark MLlib demo).

Author: _<name, student ID>_ · Course: BFT65B Big Data Analytics in Finance, National Economics University

## Requirements

* Python 3.11, packages pinned in `requirements.txt`
* JDK 17 (or 21) for PySpark. Spark 4 does not run on Java 22+. Any JDK 17 works, e.g. Eclipse Temurin 17
  unzipped to a folder; set `JAVA_HOME` to it before running Spark steps.
* ~2 GB free disk, 8 GB RAM is enough (tested on a 23 GB RAM Windows 11 laptop).

```bash
python -m venv .venv
.venv/Scripts/activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

## Run end to end

```bash
python src/download.py          # ~1 h, resumable; writes data_raw/fdic (not committed)
python src/p1_storage.py        # completeness check, Parquet lake, storage benchmark
python src/p2_quality.py        # data-quality report, clean panel + label
python src/p4_features.py       # point-in-time test, feature table, time split
python src/p5_model.py          # CV on dev, cost-based threshold, single test evaluation
# Spark steps (set JAVA_HOME first, e.g. PowerShell: $env:JAVA_HOME="D:\tools\jdk17")
python src/p3_processing.py     # pandas vs Polars vs Spark benchmark, result matching, plans
python src/p5_mllib.py          # Spark MLlib baseline demo
python src/export_excel.py      # optional: all result tables in outputs/results.xlsx
python src/predict.py           # optional: riskiest banks in the latest quarter
python src/predict.py --cert 31027   # optional: risk-score history of one bank
```

Download method/date used for the report: FDIC BankFind public API (`https://api.fdic.gov/banks`),
downloaded 2026-11-06, 170 quarters, 1,682,616 bank-quarter rows, 24,064 banks.
Every result table and figure is written to `outputs/`. Seeds are fixed (`SEED = 42` in `src/common.py`).

## Layout

| File | Part | What it does |
|---|---|---|
| `src/download.py` | 1 | API download, resumable per quarter, manifest + completeness check |
| `src/p1_storage.py` | 1 | typed schema, Hive-partitioned zstd Parquet lake, CSV vs Parquet benchmark |
| `src/p2_quality.py` | 2 | automated DQ report, exits (failure vs other), label `y`, censoring |
| `src/features.py` | 3–4 | CAMELS feature builder (Polars lazy, point-in-time) |
| `src/p3_processing.py` | 3 | same core transformation in pandas / Polars / Spark, timing, memory, plans |
| `src/p4_features.py` | 4 | leakage test, feature table, dev / gap / test split |
| `src/p5_model.py` | 5 | baseline vs gradient boosting, expanding-window CV, threshold, test once |
| `src/p5_mllib.py` | 5 | Spark ML Pipeline demo |

Columns starting with `_` in `data_proc/panel.parquet` are label-side (future) information and are
never used as features.

## Sources and AI-tool disclosure

* FDIC BankFind Suite API and field dictionaries: https://api.fdic.gov/banks/docs/
* `src/download.py` is adapted from the course starter script `fdic_download_starter.py` (BFT65B);
  the field list was extended with liquidity fields.
* Libraries: Polars, pandas, PyArrow, PySpark, scikit-learn, matplotlib.
* **Generative AI:** Claude (Anthropic, Claude Code) was used to help write and debug the pipeline code
  and to draft documentation. All design choices, results and text were reviewed by the author.

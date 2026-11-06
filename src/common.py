"""Shared paths, schema and helpers for the BFT65B early-warning pipeline."""
from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import polars as pl

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_raw" / "fdic"          # landing zone written by download.py
LAKE = ROOT / "data_lake"                 # typed, partitioned storage (Part 1)
PROC = ROOT / "data_proc"                 # clean panel, features (Parts 2-4)
OUT = ROOT / "outputs"                    # tables, figures, logs that go into the report
for _p in (LAKE, PROC, OUT):
    _p.mkdir(parents=True, exist_ok=True)

SEED = 42
LAST_MODEL_Q = "2025-06-30"   # labels after 2025Q2 are incomplete (exam rule)

KEYS = ["CERT", "REPDTE", "STNAME"]
# Every Call Report amount is stored as Float64: the API returns some columns as
# int in one quarter and float (because of nulls) in another -> schema drift.
NUMERIC = [
    "ASSET", "DEP", "DEPDOM", "EQ", "BRO", "CHBAL", "SC",
    "LNLSGR", "LNLSNET", "LNRE", "LNCI", "LNCON", "LNATRES",
    "NCLNLS", "P3ASSET", "P9ASSET", "NAASSET", "NTLNLS", "ORE",
    "NETINC", "INTINC", "EINTEXP", "NONII", "NONIX", "ELNATR",
    "ROA", "ROE", "NIMY", "RBC1AAJ", "RBCRWAJ",
    "LIAB", "COREDEP", "VOLIAB", "FREPP", "OTHBFHLB", "NUMEMP",
]
# Income-statement items are reported year-to-date (cumulative within the year).
YTD_FLOWS = ["NETINC", "INTINC", "EINTEXP", "NONII", "NONIX", "ELNATR", "NTLNLS"]

SCHEMA = {"CERT": pl.Int64, "REPDTE": pl.Date, "STNAME": pl.String,
          **{c: pl.Float64 for c in NUMERIC}}


def typed(df: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame | pl.LazyFrame:
    """Cast one raw quarter to the canonical schema (missing columns -> null)."""
    cols = df.collect_schema().names()
    exprs = []
    for name, dtype in SCHEMA.items():
        if name not in cols:
            exprs.append(pl.lit(None, dtype=dtype).alias(name))
        elif name == "REPDTE":
            exprs.append(pl.col(name).cast(pl.String).str.to_date("%Y%m%d"))
        else:
            exprs.append(pl.col(name).cast(dtype))
    return df.select(exprs)


def quarter_index(date_col: str | pl.Expr) -> pl.Expr:
    """Integer quarter counter (year*4 + quarter-1) for gap-free quarter arithmetic."""
    d = pl.col(date_col) if isinstance(date_col, str) else date_col
    return d.dt.year() * 4 + d.dt.quarter() - 1


@contextmanager
def timer(store: dict, key: str):
    t0 = time.perf_counter()
    yield
    store[key] = round(time.perf_counter() - t0, 3)


def get_spark(app: str = "bft65b"):
    """Local Spark session. Set JAVA_HOME to a JDK 17/21 before calling (see README)."""
    from pyspark.sql import SparkSession

    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    spark = (SparkSession.builder.master("local[*]").appName(app)
             .config("spark.driver.memory", "6g")
             .config("spark.sql.session.timeZone", "UTC")
             .config("spark.ui.showConsoleProgress", "false")
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def save_md(df: pl.DataFrame, path: Path, title: str = "") -> None:
    """Write a small table as Markdown so it can be pasted into the report."""
    with pl.Config(tbl_formatting="MARKDOWN", tbl_hide_dataframe_shape=True,
                   tbl_hide_column_data_types=True, tbl_rows=200, tbl_cols=50,
                   fmt_str_lengths=80, tbl_width_chars=400):
        path.write_text((f"### {title}\n\n" if title else "") + str(df) + "\n", encoding="utf-8")

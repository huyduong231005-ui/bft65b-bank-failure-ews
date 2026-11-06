"""Part 1 - verify the download and build the typed storage layout; benchmark vs raw CSV.

Run:  python src/p1_storage.py
Out:  data_lake/{financials/YEAR=*/, failures.parquet, institutions.parquet}
      outputs/p1_*.md, outputs/p1_rows_per_quarter.png
"""
from __future__ import annotations

import json
import shutil
import statistics
import time

import matplotlib.pyplot as plt
import polars as pl

from common import LAKE, OUT, RAW, save_md, typed

REPEATS = 3
BENCH = LAKE.parent / "data_bench"   # throw-away copies in different formats


# ---------------------------------------------------------------- completeness
def verify_download() -> pl.DataFrame:
    manifest = json.loads((RAW / "manifest_financials.json").read_text())
    m = pl.DataFrame([{"quarter": q, **v} for q, v in manifest.items()]).sort("quarter")
    files = sorted((RAW / "financials").glob("REPDTE=*.parquet"))
    assert len(files) == len(m), "manifest and files disagree"
    bad = m.filter(~pl.col("complete") | (pl.col("rows") != pl.col("api_total")))
    print(f"quarters={len(m)}  rows={m['rows'].sum():,}  incomplete={len(bad)}")
    assert bad.is_empty(), bad
    return m


# ---------------------------------------------------------------- lake layout
def build_lake() -> pl.DataFrame:
    """Raw per-quarter files (drifting dtypes) -> one typed dataset, Hive-partitioned by YEAR."""
    frames = [typed(pl.read_parquet(f)) for f in sorted((RAW / "financials").glob("*.parquet"))]
    fin = pl.concat(frames).sort("CERT", "REPDTE")
    dup = fin.select(pl.struct("CERT", "REPDTE").is_duplicated().sum()).item()
    assert dup == 0, f"{dup} duplicate CERT-REPDTE rows"

    target = LAKE / "financials"
    shutil.rmtree(target, ignore_errors=True)
    # ponytail: YEAR partitions (43 dirs, ~40k rows each) - big enough for good
    # compression, small enough for pruning. Per-quarter files would be 170 tiny files.
    (fin.with_columns(pl.col("REPDTE").dt.year().alias("YEAR"))
        .write_parquet(target, partition_by="YEAR", compression="zstd",
                       statistics=True, row_group_size=50_000))

    fails = pl.read_parquet(RAW / "failures.parquet").with_columns(
        pl.col("CERT").cast(pl.Int64),
        pl.col("FAILDATE").str.to_date("%m/%d/%Y"),
        pl.col("FAILYR").cast(pl.Int32))
    inst = pl.read_parquet(RAW / "institutions.parquet").with_columns(
        pl.col("CERT").cast(pl.Int64),
        *[pl.col(c).str.to_date("%m/%d/%Y", strict=False) for c in ("ESTYMD", "ENDEFYMD", "INSDATE")],
        pl.col("CHANGEC1").cast(pl.Int32))
    fails.write_parquet(LAKE / "failures.parquet", compression="zstd")
    inst.write_parquet(LAKE / "institutions.parquet", compression="zstd")
    print(f"lake: financials {fin.shape}, failures {fails.shape}, institutions {inst.shape}")
    return fin


# ---------------------------------------------------------------- benchmark
def dir_mb(path) -> float:
    files = [path] if path.is_file() else list(path.rglob("*.*"))
    return sum(f.stat().st_size for f in files) / 2**20


def median_time(fn) -> float:
    runs = []
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        fn()
        runs.append(time.perf_counter() - t0)
    return round(statistics.median(runs), 3)


def benchmark(fin: pl.DataFrame) -> pl.DataFrame:
    shutil.rmtree(BENCH, ignore_errors=True)
    BENCH.mkdir()
    lake = LAKE / "financials"
    layouts = {
        "CSV (raw text)": BENCH / "fin.csv",
        "CSV + gzip": BENCH / "fin.csv.gz",
        "Parquet snappy, 1 file": BENCH / "fin_snappy.parquet",
        "Parquet zstd, 1 file": BENCH / "fin_zstd.parquet",
        "Parquet zstd, YEAR partitions (chosen)": lake,
    }
    write = {
        "CSV (raw text)": lambda p: fin.write_csv(p),
        "CSV + gzip": lambda p: p.write_bytes(__import__("gzip").compress(fin.write_csv().encode(), 6)),
        "Parquet snappy, 1 file": lambda p: fin.write_parquet(p, compression="snappy"),
        "Parquet zstd, 1 file": lambda p: fin.write_parquet(p, compression="zstd"),
        "Parquet zstd, YEAR partitions (chosen)": None,  # already written by build_lake
    }

    def scan(name, p):
        if name.startswith("CSV"):
            return pl.scan_csv(p, schema_overrides={"REPDTE": pl.Date}, try_parse_dates=True)
        return pl.scan_parquet(p, hive_partitioning=p.is_dir())

    rows = []
    for name, p in layouts.items():
        t_write = median_time(lambda: write[name](p)) if write[name] else None
        lf = lambda: scan(name, p)  # noqa: E731
        rows.append({
            "layout": name,
            "size_MB": round(dir_mb(p), 1),
            "write_s": t_write,
            "read_all_s": median_time(lambda: lf().collect()),
            "read_3_cols_s": median_time(lambda: lf().select("CERT", "REPDTE", "ASSET").collect()),
            "filter_2008_s": median_time(lambda: lf().filter(pl.col("REPDTE").dt.year() == 2008)
                                         .select("CERT", "ASSET", "EQ").collect()),
        })
        print(rows[-1])
    res = pl.DataFrame(rows)
    base = res.filter(pl.col("layout") == "CSV (raw text)").row(0, named=True)
    res = res.with_columns(
        (pl.col("size_MB") / base["size_MB"]).round(3).alias("size_vs_csv"),
        (base["filter_2008_s"] / pl.col("filter_2008_s")).round(1).alias("filter_speedup_vs_csv"))
    shutil.rmtree(BENCH, ignore_errors=True)
    return res


def main() -> None:
    m = verify_download()
    fin = build_lake()

    per_q = fin.group_by("REPDTE").agg(pl.len().alias("banks")).sort("REPDTE")
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(per_q["REPDTE"], per_q["banks"])
    ax.set_title("Reporting institutions per quarter (FDIC Call Reports)")
    ax.set_ylabel("banks")
    fig.tight_layout()
    fig.savefig(OUT / "p1_rows_per_quarter.png", dpi=150)

    summary = pl.DataFrame({
        "metric": ["quarters", "first quarter", "last quarter", "panel rows", "distinct banks",
                   "duplicate CERT-REPDTE", "quarters with rows != API total",
                   "failures rows", "institutions rows"],
        "value": [str(len(m)), str(fin["REPDTE"].min()), str(fin["REPDTE"].max()),
                  f"{fin.height:,}", f"{fin['CERT'].n_unique():,}", "0", "0",
                  f"{pl.scan_parquet(LAKE / 'failures.parquet').select(pl.len()).collect().item():,}",
                  f"{pl.scan_parquet(LAKE / 'institutions.parquet').select(pl.len()).collect().item():,}"],
    })
    save_md(summary, OUT / "p1_completeness.md", "Download completeness")
    res = benchmark(fin)
    save_md(res, OUT / "p1_storage_benchmark.md",
            f"Storage layouts, {fin.height:,} rows x {fin.width} cols (median of {REPEATS} runs)")
    print(res)


if __name__ == "__main__":
    main()

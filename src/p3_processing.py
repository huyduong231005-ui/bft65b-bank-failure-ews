"""Part 3 - the same core transformation in pandas, Polars (eager / lazy / streaming) and PySpark.

Core step (= the heart of the feature pipeline):
  read lake -> drop ASSET<=0 -> annualise YTD flows -> 5 CAMELS ratios -> exact q-4 self-join
  -> year-on-year changes -> within-quarter peer rank -> failure label (fails in (q, q+4]).

Each engine runs in a fresh subprocess so wall time and peak memory (Windows peak working set)
are measured fairly.  Run:  python src/p3_processing.py
Needs JAVA_HOME pointing to JDK 17 for the Spark runs (see README).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import polars as pl

from common import LAKE, OUT, ROOT, get_spark, save_md

COLS = ["CERT", "REPDTE", "ASSET", "EQ", "NCLNLS", "LNLSGR", "NETINC", "NTLNLS", "BRO", "DEP"]
OUT_COLS = ["CERT", "REPDTE", "cap_eq_ta", "aq_noncurrent", "earn_roa", "aq_nco", "liq_brokered_dep",
            "d4_cap_eq_ta", "d4_aq_noncurrent", "pr_cap_eq_ta", "y"]
SCALED = ROOT / "data_bench"
SCALES = [1, 4, 16]
REPEATS = 3


def src_path(scale: int) -> Path:
    return LAKE / "financials" if scale == 1 else SCALED / f"x{scale}"


def make_scaled(scale: int) -> None:
    """Synthetic scale-up: k copies of the panel with shifted CERTs (failures copied too)."""
    target = SCALED / f"x{scale}"
    if target.exists():
        return
    fin = pl.read_parquet(LAKE / "financials", hive_partitioning=True)
    big = pl.concat([fin.with_columns(pl.col("CERT") + i * 1_000_000) for i in range(scale)])
    big.write_parquet(target, partition_by="YEAR", compression="zstd")
    f = pl.read_parquet(LAKE / "failures.parquet")
    pl.concat([f.with_columns(pl.col("CERT") + i * 1_000_000) for i in range(scale)]) \
        .write_parquet(SCALED / f"x{scale}_failures.parquet")


def fail_path(scale: int) -> Path:
    return LAKE / "failures.parquet" if scale == 1 else SCALED / f"x{scale}_failures.parquet"


# ====================================================================== Polars
def core_polars(scale: int, lazy: bool = True, streaming: bool = False) -> pl.DataFrame:
    if lazy:
        fin = pl.scan_parquet(src_path(scale), hive_partitioning=True)
        fails = pl.scan_parquet(fail_path(scale))
    else:
        fin = pl.read_parquet(src_path(scale), hive_partitioning=True)
        fails = pl.read_parquet(fail_path(scale))
    q = pl.col("REPDTE").dt.year() * 4 + pl.col("REPDTE").dt.quarter() - 1
    pct = lambda n, d: pl.when(pl.col(d) > 0).then(pl.col(n) / pl.col(d) * 100)  # noqa: E731

    base = (fin.select(COLS).filter(pl.col("ASSET") > 0)
            .with_columns(q.alias("q"), (4 / pl.col("REPDTE").dt.quarter()).alias("ann"))
            .with_columns(pl.col("NETINC") * pl.col("ann"), pl.col("NTLNLS") * pl.col("ann"))
            .with_columns(cap_eq_ta=pct("EQ", "ASSET"), aq_noncurrent=pct("NCLNLS", "LNLSGR"),
                          earn_roa=pct("NETINC", "ASSET"), aq_nco=pct("NTLNLS", "LNLSGR"),
                          liq_brokered_dep=pct("BRO", "DEP")))
    lag = base.select("CERT", (pl.col("q") + 4).alias("q"),
                      pl.col("cap_eq_ta").alias("l4_eq"), pl.col("aq_noncurrent").alias("l4_ncl"))
    ev = (fails.filter((pl.col("RESTYPE") == "FAILURE") & (pl.col("FAILDATE") >= pl.date(1984, 1, 1)))
          .select("CERT", (pl.col("FAILDATE").dt.year() * 4 + pl.col("FAILDATE").dt.quarter() - 1).alias("fq")))
    lab = (base.select("CERT", "q").join(ev, on="CERT")
           .filter((pl.col("fq") - pl.col("q")).is_between(1, 4))
           .select("CERT", "q").unique().with_columns(pl.lit(1, pl.Int8).alias("y")))
    res = (base.join(lag, on=["CERT", "q"], how="left")
           .with_columns(d4_cap_eq_ta=pl.col("cap_eq_ta") - pl.col("l4_eq"),
                         d4_aq_noncurrent=pl.col("aq_noncurrent") - pl.col("l4_ncl"),
                         pr_cap_eq_ta=pl.col("cap_eq_ta").rank("average").over("REPDTE")
                         / pl.col("cap_eq_ta").count().over("REPDTE"))
           .join(lab, on=["CERT", "q"], how="left")
           .with_columns(pl.col("y").fill_null(0))
           .select(OUT_COLS))
    if lazy:
        return res, res.collect(engine="streaming" if streaming else "auto")
    return None, res


# ====================================================================== pandas
def core_pandas(scale: int):
    import numpy as np
    import pandas as pd

    # partitioning=None: YEAR is also stored inside the files, so skip Hive inference
    fin = pd.read_parquet(src_path(scale), columns=COLS, partitioning=None)
    fails = pd.read_parquet(fail_path(scale))
    fin = fin[fin["ASSET"] > 0].copy()
    d = pd.to_datetime(fin["REPDTE"])
    fin["q"] = d.dt.year * 4 + d.dt.quarter - 1
    ann = 4 / d.dt.quarter
    fin["NETINC"] *= ann
    fin["NTLNLS"] *= ann

    def pct(n, den):
        return np.where(fin[den] > 0, fin[n] / fin[den].where(fin[den] > 0) * 100, np.nan)

    fin["cap_eq_ta"] = pct("EQ", "ASSET")
    fin["aq_noncurrent"] = pct("NCLNLS", "LNLSGR")
    fin["earn_roa"] = pct("NETINC", "ASSET")
    fin["aq_nco"] = pct("NTLNLS", "LNLSGR")
    fin["liq_brokered_dep"] = pct("BRO", "DEP")
    lag = fin[["CERT", "q", "cap_eq_ta", "aq_noncurrent"]].rename(
        columns={"cap_eq_ta": "l4_eq", "aq_noncurrent": "l4_ncl"})
    lag["q"] += 4
    fin = fin.merge(lag, on=["CERT", "q"], how="left")
    fin["d4_cap_eq_ta"] = fin["cap_eq_ta"] - fin["l4_eq"]
    fin["d4_aq_noncurrent"] = fin["aq_noncurrent"] - fin["l4_ncl"]
    fin["pr_cap_eq_ta"] = fin.groupby("REPDTE")["cap_eq_ta"].rank(method="average", pct=True)

    ev = fails[(fails["RESTYPE"] == "FAILURE") & (pd.to_datetime(fails["FAILDATE"]) >= "1984-01-01")]
    fd = pd.to_datetime(ev["FAILDATE"])
    ev = pd.DataFrame({"CERT": ev["CERT"].values, "fq": (fd.dt.year * 4 + fd.dt.quarter - 1).values})
    lab = fin[["CERT", "q"]].merge(ev, on="CERT")
    lab = lab[(lab["fq"] - lab["q"]).between(1, 4)][["CERT", "q"]].drop_duplicates()
    lab["y"] = 1
    fin = fin.merge(lab, on=["CERT", "q"], how="left")
    fin["y"] = fin["y"].fillna(0).astype("int8")
    return fin[OUT_COLS]


# ====================================================================== Spark
def core_spark(spark, scale: int):
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    # explicit file list: listing a directory on Windows needs Hadoop's winutils native library
    fin = spark.read.parquet(*[str(p) for p in sorted(src_path(scale).rglob("*.parquet"))])
    fails = spark.read.parquet(str(fail_path(scale)))
    pct = lambda n, d: F.when(F.col(d) > 0, F.col(n) / F.col(d) * 100)  # noqa: E731
    base = (fin.select(*COLS).filter(F.col("ASSET") > 0)
            .withColumn("q", F.year("REPDTE") * 4 + F.quarter("REPDTE") - 1)
            .withColumn("ann", F.lit(4.0) / F.quarter("REPDTE"))
            .withColumn("NETINC", F.col("NETINC") * F.col("ann"))
            .withColumn("NTLNLS", F.col("NTLNLS") * F.col("ann"))
            .withColumn("cap_eq_ta", pct("EQ", "ASSET"))
            .withColumn("aq_noncurrent", pct("NCLNLS", "LNLSGR"))
            .withColumn("earn_roa", pct("NETINC", "ASSET"))
            .withColumn("aq_nco", pct("NTLNLS", "LNLSGR"))
            .withColumn("liq_brokered_dep", pct("BRO", "DEP")))
    lag = base.select("CERT", (F.col("q") + 4).alias("q"),
                      F.col("cap_eq_ta").alias("l4_eq"), F.col("aq_noncurrent").alias("l4_ncl"))
    ev = (fails.filter((F.col("RESTYPE") == "FAILURE") & (F.col("FAILDATE") >= F.lit("1984-01-01").cast("date")))
          .select("CERT", (F.year("FAILDATE") * 4 + F.quarter("FAILDATE") - 1).alias("fq")))
    lab = (base.select("CERT", "q").join(ev, "CERT")
           .filter((F.col("fq") - F.col("q")).between(1, 4))
           .select("CERT", "q").distinct().withColumn("y", F.lit(1)))
    # average rank / non-null count (same definition as Polars and pandas):
    # min rank (nulls last) + (ties - 1) / 2
    w_q = Window.partitionBy("REPDTE")
    w_ord = Window.partitionBy("REPDTE").orderBy(F.col("cap_eq_ta").asc_nulls_last())
    w_tie = Window.partitionBy("REPDTE", "cap_eq_ta")
    avg_rank = F.rank().over(w_ord) + (F.count("*").over(w_tie) - 1) / 2
    res = (base.join(lag, ["CERT", "q"], "left")
           .withColumn("d4_cap_eq_ta", F.col("cap_eq_ta") - F.col("l4_eq"))
           .withColumn("d4_aq_noncurrent", F.col("aq_noncurrent") - F.col("l4_ncl"))
           .withColumn("pr_cap_eq_ta", F.when(F.col("cap_eq_ta").isNotNull(),
                                              avg_rank / F.count("cap_eq_ta").over(w_q)))
           .join(lab, ["CERT", "q"], "left")
           .withColumn("y", F.coalesce(F.col("y"), F.lit(0)))
           .select(*OUT_COLS))
    return res


# ====================================================================== runner
def run_child(engine: str, scale: int) -> dict:
    import psutil

    t0 = time.perf_counter()
    if engine == "pandas":
        out = pl.from_pandas(core_pandas(scale))
    elif engine == "polars_eager":
        _, out = core_polars(scale, lazy=False)
    elif engine == "polars_lazy":
        _, out = core_polars(scale, lazy=True)
    elif engine == "polars_streaming":
        _, out = core_polars(scale, lazy=True, streaming=True)
    elif engine == "spark":
        from pyspark.sql import functions as F

        spark = get_spark("p3")
        t0 = time.perf_counter()          # JVM start-up excluded (a cluster keeps it warm)
        agg = (core_spark(spark, scale)
               .agg(*[F.sum(c).alias(c) for c in OUT_COLS[2:]], F.count("*").alias("rows"))
               .collect()[0].asDict())
        secs = time.perf_counter() - t0
        # peak of the JVM child processes = Spark's real footprint
        jvm = max((c.memory_info().peak_wset for c in psutil.Process().children(recursive=True)), default=0)
        spark.stop()
        return {"engine": engine, "scale": scale, "seconds": round(secs, 2),
                "peak_mb": round(jvm / 2**20), "rows": agg.pop("rows"),
                "sums": {k: float(v or 0) for k, v in agg.items()}}
    secs = time.perf_counter() - t0
    sums = out.select([pl.col(c).cast(pl.Float64).sum() for c in OUT_COLS[2:]]).row(0, named=True)
    return {"engine": engine, "scale": scale, "seconds": round(secs, 2),
            "peak_mb": round(psutil.Process().memory_info().peak_wset / 2**20),
            "rows": out.height, "sums": sums}


def spawn(engine: str, scale: int) -> dict:
    cmd = [sys.executable, __file__, "--child", engine, "--scale", str(scale)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    line = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")]
    if proc.returncode or not line:
        return {"engine": engine, "scale": scale, "seconds": None, "peak_mb": None,
                "rows": None, "error": proc.stderr[-300:]}
    return json.loads(line[-1])


def check_match() -> pl.DataFrame:
    """Row-level comparison pandas vs Polars, and aggregate comparison vs Spark (scale 1)."""
    _, pol = core_polars(1)
    pdf = pl.from_pandas(core_pandas(1)).with_columns(pl.col("REPDTE").cast(pl.Date))
    j = pol.join(pdf, on=["CERT", "REPDTE"], suffix="_pd", how="full", coalesce=True)
    rows = []
    for c in OUT_COLS[2:]:
        diff = (pl.col(c) - pl.col(f"{c}_pd")).abs()
        rows.append({"column": c,
                     "max |polars - pandas|": j.select(diff.max()).item(),
                     "null mismatches": j.select((pl.col(c).is_null() != pl.col(f"{c}_pd").is_null()).sum()).item()})
    spark = get_spark("p3-check")
    sp = pl.from_pandas(core_spark(spark, 1).toPandas()).with_columns(pl.col("REPDTE").cast(pl.Date))
    js = pol.join(sp, on=["CERT", "REPDTE"], suffix="_sp", how="full", coalesce=True)
    for r in rows:
        c = r["column"]
        r["max |polars - spark|"] = js.select((pl.col(c) - pl.col(f"{c}_sp")).abs().max()).item()
        r["null mismatches spark"] = js.select((pl.col(c).is_null() != pl.col(f"{c}_sp").is_null()).sum()).item()
    rows.append({"column": "rows", "max |polars - pandas|": pol.height - pdf.height,
                 "null mismatches": 0, "max |polars - spark|": pol.height - sp.height, "null mismatches spark": 0})
    plan = core_spark(spark, 1)
    (OUT / "p3_spark_plan.txt").write_text(plan._jdf.queryExecution().explainString(
        spark._jvm.org.apache.spark.sql.execution.ExplainMode.fromString("formatted")), encoding="utf-8")
    spark.stop()
    return pl.DataFrame(rows)


def explain_polars() -> None:
    lf, _ = core_polars(1)
    (OUT / "p3_polars_plan_naive.txt").write_text(lf.explain(optimized=False), encoding="utf-8")
    (OUT / "p3_polars_plan_optimized.txt").write_text(lf.explain(), encoding="utf-8")


def main() -> None:
    SCALED.mkdir(exist_ok=True)
    for s in SCALES[1:]:
        make_scaled(s)
    explain_polars()
    match = check_match()
    save_md(match, OUT / "p3_results_match.md", "Do the engines produce the same numbers? (scale 1)")
    print(match)

    results = []
    for scale in SCALES:
        for engine in ["pandas", "polars_eager", "polars_lazy", "polars_streaming", "spark"]:
            runs = [spawn(engine, scale) for _ in range(REPEATS if scale == 1 else 1)]
            ok = [r for r in runs if r.get("seconds") is not None]
            best = sorted(ok, key=lambda r: r["seconds"])[len(ok) // 2] if ok else runs[0]
            print(best)
            results.append({k: best.get(k) for k in ("engine", "scale", "seconds", "peak_mb", "rows")}
                           | {"error": (best.get("error") or "")[:80]})
    res = pl.DataFrame(results)
    res.write_csv(OUT / "p3_benchmark.csv")
    save_md(res, OUT / "p3_benchmark.md",
            "Core transformation: wall time (median of 3 at x1) and peak memory, fresh process per run")
    shutil.rmtree(SCALED, ignore_errors=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--child")
    ap.add_argument("--scale", type=int, default=1)
    a = ap.parse_args()
    if a.child:
        print(json.dumps(run_child(a.child, a.scale), default=str))
    else:
        main()

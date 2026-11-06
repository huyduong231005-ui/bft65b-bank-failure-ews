"""Part 2 - automated data-quality report + clean, point-in-time bank-quarter panel with label.

Run:  python src/p2_quality.py      (needs p1_storage.py first)
Out:  outputs/p2_*.md, outputs/p2_missing_by_era.png, data_proc/panel.parquet

Label (exam definition): y[i,q] = 1 if bank i FAILS in (q, q+4 quarters]; mergers are not failures.
Columns starting with "_" are label-side information (future) and must never be used as features.
"""
from __future__ import annotations

import json

import matplotlib.pyplot as plt
import polars as pl

from common import (LAKE, LAST_MODEL_Q, NUMERIC, OUT, PROC, RAW, YTD_FLOWS,
                    quarter_index, save_md)

HORIZON = 4  # quarters
RBC_RATIOS = ("RBC1AAJ", "RBCRWAJ")
LAST_Q = pl.lit(LAST_MODEL_Q).str.to_date()


def load() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    fin = pl.read_parquet(LAKE / "financials", hive_partitioning=True).drop("YEAR")
    fails = pl.read_parquet(LAKE / "failures.parquet")
    inst = pl.read_parquet(LAKE / "institutions.parquet")
    return fin, fails, inst


# =============================================================== audit checks
def schema_drift() -> pl.DataFrame:
    """Columns whose dtype differs between raw quarterly files."""
    rows = []
    for f in sorted((RAW / "financials").glob("*.parquet")):
        for col, dt in pl.read_parquet_schema(f).items():
            rows.append({"column": col, "dtype": str(dt)})
    return (pl.DataFrame(rows).group_by("column")
            .agg(pl.col("dtype").unique().sort().str.join(" / ").alias("raw dtypes"),
                 pl.col("dtype").n_unique().alias("n_dtypes"))
            .filter(pl.col("n_dtypes") > 1).sort("column"))


def missing_by_era(fin: pl.DataFrame) -> pl.DataFrame:
    era = (pl.when(pl.col("REPDTE").dt.year() < 1990).then(pl.lit("1984-89"))
           .when(pl.col("REPDTE").dt.year() < 2001).then(pl.lit("1990-2000"))
           .when(pl.col("REPDTE").dt.year() < 2011).then(pl.lit("2001-10"))
           .otherwise(pl.lit("2011-26")))
    return (fin.with_columns(era.alias("era")).group_by("era")
            .agg([(pl.col(c).null_count() / pl.len() * 100).round(1).alias(c) for c in NUMERIC])
            .sort("era"))


def zeros_by_era(fin: pl.DataFrame) -> pl.DataFrame:
    """Exact zeros: legitimate for BRO/FREPP, but a 'not reported' code for capital ratios."""
    cols = ["RBC1AAJ", "RBCRWAJ", "BRO", "FREPP", "P9ASSET", "NAASSET", "COREDEP", "VOLIAB"]
    return (fin.group_by((pl.col("REPDTE").dt.year() // 5 * 5).alias("from year"))
            .agg([((pl.col(c) == 0).mean() * 100).round(1).alias(c) for c in cols]).sort("from year"))


def plot_missing(miss: pl.DataFrame) -> None:
    cols = [c for c in NUMERIC if miss[c].max() > 0]
    fig, ax = plt.subplots(figsize=(10, 3.2))
    im = ax.imshow(miss.select(cols).to_numpy(), aspect="auto", cmap="Reds", vmin=0, vmax=100)
    ax.set_xticks(range(len(cols)), cols, rotation=90, fontsize=7)
    ax.set_yticks(range(miss.height), miss["era"].to_list())
    fig.colorbar(im, label="% missing")
    ax.set_title("Missing values by era (structural: fields introduced later)")
    fig.tight_layout()
    fig.savefig(OUT / "p2_missing_by_era.png", dpi=150)


def ytd_pattern(fin: pl.DataFrame) -> pl.DataFrame:
    """Median NETINC/ASSET by quarter of year: rising Q1->Q4 => cumulative YTD reporting."""
    return (fin.filter(pl.col("ASSET") > 0)
            .group_by(pl.col("REPDTE").dt.quarter().alias("quarter_of_year"))
            .agg((pl.col("NETINC") / pl.col("ASSET") * 100).median().round(3).alias("median NETINC/ASSET %"),
                 (pl.col("INTINC") / pl.col("ASSET") * 100).median().round(3).alias("median INTINC/ASSET %"),
                 pl.col("ROA").median().round(3).alias("median ROA % (already annualised)"))
            .sort("quarter_of_year"))


def value_checks(fin: pl.DataFrame) -> pl.DataFrame:
    n = fin.height
    checks = {
        "duplicate CERT-REPDTE": pl.struct("CERT", "REPDTE").is_duplicated(),
        "ASSET <= 0 or null": (pl.col("ASSET") <= 0) | pl.col("ASSET").is_null(),
        "EQ > ASSET": pl.col("EQ") > pl.col("ASSET"),
        "EQ < 0 (insolvent book equity)": pl.col("EQ") < 0,
        "|ASSET - LIAB - EQ| > 1% of ASSET": (pl.col("ASSET") - pl.col("LIAB") - pl.col("EQ")).abs()
        > 0.01 * pl.col("ASSET"),
        "negative stock (DEP, LNLSGR, NCLNLS, SC, CHBAL, LNATRES)":
            pl.any_horizontal([pl.col(c) < 0 for c in ("DEP", "LNLSGR", "NCLNLS", "SC", "CHBAL", "LNATRES")]),
        "LNLSGR > ASSET": pl.col("LNLSGR") > pl.col("ASSET"),
        "|ROA| > 20%": pl.col("ROA").abs() > 20,
        "|ROE| > 200%": pl.col("ROE").abs() > 200,
        "ROE null while ROA present": pl.col("ROE").is_null() & pl.col("ROA").is_not_null(),
        "RBC1AAJ > 100 or < -100": (pl.col("RBC1AAJ") > 100) | (pl.col("RBC1AAJ") < -100),
        "RBC1AAJ == 0 while EQ > 0 (zero = not reported)": (pl.col("RBC1AAJ") == 0) & (pl.col("EQ") > 0),
        "RBCRWAJ == 0 while EQ > 0 (zero = not reported)": (pl.col("RBCRWAJ") == 0) & (pl.col("EQ") > 0),
        "tiny bank (ASSET < $5m)": pl.col("ASSET") < 5_000,
    }
    out = fin.select([e.fill_null(False).sum().alias(k) for k, e in checks.items()])
    return (out.transpose(include_header=True, header_name="check", column_names=["rows"])
            .with_columns((pl.col("rows") / n * 100).round(3).alias("% of rows")))


def reporting_gaps(fin: pl.DataFrame) -> pl.DataFrame:
    g = (fin.with_columns(quarter_index("REPDTE").alias("q")).group_by("CERT")
         .agg(pl.len().alias("n"), (pl.col("q").max() - pl.col("q").min() + 1).alias("span")))
    return pl.DataFrame({
        "metric": ["banks", "banks with >=1 missing quarter inside their history",
                   "missing bank-quarters inside histories", "banks with < 4 quarters of history"],
        "value": [g.height, g.filter(pl.col("span") > pl.col("n")).height,
                  int((g["span"] - g["n"]).sum()), g.filter(pl.col("n") < 4).height]})


# =============================================================== exits & label
def failure_events(fails: pl.DataFrame) -> pl.DataFrame:
    # exam scope: failures 1984Q1-2026Q2 (same scope as Financials; reruns on later dates give same result)
    return (fails.filter((pl.col("RESTYPE") == "FAILURE")
                         & pl.col("FAILDATE").is_between(pl.date(1984, 1, 1), pl.date(2026, 6, 30)))
            .select("CERT", "FAILDATE", "COST", "QBFASSET")
            .with_columns(quarter_index("FAILDATE").alias("fail_q")))


def failure_coverage(fin: pl.DataFrame, fev: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """How many failures can be seen in the panel, and how long before failure is the last report?"""
    reps = fin.select("CERT", quarter_index("REPDTE").alias("q"))
    joined = fev.join(reps, on="CERT", how="left")
    last_before = (joined.group_by("CERT", "FAILDATE", "fail_q")
                   .agg(pl.col("q").filter(pl.col("q") < pl.col("fail_q")).max().alias("last_q"),
                        (pl.col("q") >= pl.col("fail_q")).sum().alias("reports_on_or_after_fail")))
    lag = last_before.with_columns((pl.col("fail_q") - pl.col("last_q")).alias("gap_q"))
    bucket = (pl.when(pl.col("gap_q").is_null()).then(pl.lit("not in Financials"))
              .when(pl.col("gap_q") <= 1).then(pl.lit("last report 1 quarter before"))
              .when(pl.col("gap_q") <= HORIZON).then(pl.lit("last report 2-4 quarters before"))
              .otherwise(pl.lit("last report > 4 quarters before (invisible)")))
    cov = (lag.with_columns(bucket.alias("case"))
           .group_by("case").agg(pl.len().alias("failures"),
                                 (pl.col("reports_on_or_after_fail") > 0).sum().alias("also report after failure"))
           .sort("failures", descending=True))
    return cov, lag


def build_panel(fin: pl.DataFrame, fev: pl.DataFrame, inst: pl.DataFrame) -> pl.DataFrame:
    max_q = fin.select(quarter_index("REPDTE").max()).item()
    p = (fin.filter(pl.col("ASSET") > 0)
         .with_columns(quarter_index("REPDTE").alias("q"),
                       pl.col("REPDTE").dt.quarter().alias("qtr")))

    # YTD income items -> annualised, using only the current report (point-in-time safe)
    p = p.with_columns([(pl.col(c) * 4 / pl.col("qtr")).alias(c) for c in YTD_FLOWS])
    # capital ratios coded 0 when not reported (pre-1990 Basel I, post-2020 CBLR banks) -> null
    p = p.with_columns([pl.when((pl.col(c) == 0) & (pl.col("EQ") > 0)).then(None).otherwise(pl.col(c)).alias(c)
                        for c in RBC_RATIOS])

    # first FAILURE of each bank strictly after each report: label + drop post-failure rows
    nxt = (p.select("CERT", "q").join(fev.select("CERT", "fail_q", "FAILDATE"), on="CERT")
           .filter(pl.col("fail_q") > pl.col("q"))
           .group_by("CERT", "q").agg(pl.col("fail_q").min(), pl.col("FAILDATE").min()))
    first_fail = fev.group_by("CERT").agg(pl.col("fail_q").min().alias("first_fail_q"))
    p = (p.join(nxt, on=["CERT", "q"], how="left")
         .join(first_fail, on="CERT", how="left")
         # rows on/after a failure belong to a bridge/acquirer reusing the CERT: not this bank
         .filter(pl.col("first_fail_q").is_null() | (pl.col("q") < pl.col("first_fail_q")))
         .with_columns(((pl.col("fail_q") - pl.col("q")).is_between(1, HORIZON)).fill_null(False)
                       .cast(pl.Int8).alias("y"),
                       (pl.col("REPDTE") <= LAST_Q).alias("label_complete")))

    # exit type per bank (label-side, future information)
    last = p.group_by("CERT").agg(pl.col("q").max().alias("last_q"),
                                  pl.col("first_fail_q").first())
    exit_type = (pl.when((pl.col("first_fail_q") - pl.col("last_q")).is_between(1, HORIZON))
                 .then(pl.lit("failure"))
                 .when(pl.col("last_q") == max_q).then(pl.lit("active"))
                 .otherwise(pl.lit("other exit (merger, liquidation, charter change)")))
    last = last.with_columns(exit_type.alias("_exit_type")).select("CERT", "_exit_type")

    p = (p.join(last, on="CERT", how="left")
         .with_columns(pl.col("q").rank("ordinal").over("CERT").cast(pl.Int32).alias("n_hist"))
         .rename({"FAILDATE": "_next_fail_date", "fail_q": "_next_fail_q"})
         .drop("first_fail_q")
         .sort("CERT", "REPDTE"))
    return p


def exit_crosstab(panel: pl.DataFrame, inst: pl.DataFrame) -> pl.DataFrame:
    """Data-driven check of CHANGEC1 (institution 'why it stopped') against our exit typing."""
    banks = panel.select("CERT", "_exit_type").unique()
    return (banks.join(inst.select("CERT", "CHANGEC1"), on="CERT", how="left")
            .group_by("_exit_type", "CHANGEC1").len()
            .sort("_exit_type", "len", descending=[False, True])
            .group_by("_exit_type", maintain_order=True).head(5))


def main() -> None:
    fin, fails, inst = load()
    fev = failure_events(fails)

    drift = schema_drift()
    miss = missing_by_era(fin)
    plot_missing(miss)
    checks = value_checks(fin)
    gaps = reporting_gaps(fin)
    ytd = ytd_pattern(fin)
    cov, _ = failure_coverage(fin, fev)
    panel = build_panel(fin, fev, inst)
    xtab = exit_crosstab(panel, inst)

    restype = (fails.filter(pl.col("FAILDATE") >= pl.date(1984, 1, 1))
               .group_by("RESTYPE").agg(pl.len().alias("events"),
                                        pl.col("COST").null_count().alias("COST missing")))
    multi = fails.filter(pl.col("CERT").is_duplicated()).select("CERT").n_unique()
    m = panel.filter(pl.col("label_complete"))
    summary = pl.DataFrame({
        "metric": ["raw panel rows", "rows dropped: ASSET <= 0 / null", "rows dropped: on/after failure",
                   "clean panel rows", "rows with complete label (<= 2025Q2)", "positive rows (y=1)",
                   "failed banks with >=1 positive row", "CERTs with several failure/assistance events"],
        "value": [fin.height, fin.filter(~(pl.col("ASSET") > 0)).height,
                  fin.filter(pl.col("ASSET") > 0).height - panel.height, panel.height, m.height,
                  int(m["y"].sum()), m.filter(pl.col("y") == 1)["CERT"].n_unique(), multi]})
    banks = panel.group_by("_exit_type").agg(pl.col("CERT").n_unique().alias("banks"))

    report = OUT / "p2_dq_report.md"
    parts = [("Panel construction summary", summary), ("Bank exits (treated separately)", banks),
             ("Failures table by resolution type (1984+)", restype),
             ("Failure coverage in Financials (RESTYPE=FAILURE, 1984+)", cov),
             ("Value / consistency checks on raw panel", checks), ("Reporting gaps", gaps),
             ("Schema drift between raw quarterly files", drift),
             ("YTD reporting of income items", ytd), ("Missing % by era", miss),
             ("Exact-zero % by period (zero used as 'not reported')", zeros_by_era(fin)),
             ("CHANGEC1 codes by derived exit type (top 5)", xtab)]
    tmp = OUT / "_tmp.md"
    text = ["# Automated data-quality report\n"]
    for title, df in parts:
        save_md(df, tmp, title)
        text.append(tmp.read_text(encoding="utf-8"))
    tmp.unlink()
    report.write_text("\n".join(text), encoding="utf-8")

    panel.write_parquet(PROC / "panel.parquet", compression="zstd")
    (OUT / "p2_summary.json").write_text(json.dumps(dict(zip(summary["metric"], summary["value"]))))
    print(report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()

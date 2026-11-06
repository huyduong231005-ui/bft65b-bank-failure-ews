"""Part 4 - leak-free feature table joined with the label, time split, point-in-time test.

Run:  python src/p4_features.py      (needs p2_quality.py first)
Out:  data_proc/features.parquet, outputs/p4_*.md
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from common import LAST_MODEL_Q, OUT, PROC, SEED, save_md
from features import build_features, feature_names

DEV_END, TEST_START = "2008-12-31", "2010-03-31"   # 2009 = 4-quarter gap
d = lambda s: pl.lit(s).str.to_date()  # noqa: E731


def split_expr() -> pl.Expr:
    return (pl.when(pl.col("REPDTE") <= d(DEV_END)).then(pl.lit("dev"))
            .when(pl.col("REPDTE") >= d(TEST_START)).then(pl.lit("test"))
            .otherwise(pl.lit("gap")))


def point_in_time_test(panel: pl.DataFrame, cutoff: str = "2000-12-31") -> int:
    """Scramble every report after `cutoff`; features up to `cutoff` must not change."""
    rng = np.random.default_rng(SEED)
    num = [c for c, t in panel.schema.items() if t == pl.Float64]
    future = panel["REPDTE"] > pl.Series([cutoff]).str.to_date()[0]
    noisy = panel.with_columns([pl.when(pl.Series(future)).then(pl.col(c) * pl.Series(rng.uniform(0.1, 10, panel.height)))
                                .otherwise(pl.col(c)).alias(c) for c in num])
    # joins do not keep row order in Polars 2 -> compare on sorted keys
    a = build_features(panel.lazy()).filter(pl.col("REPDTE") <= d(cutoff)).sort("CERT", "REPDTE").collect()
    b = build_features(noisy.lazy()).filter(pl.col("REPDTE") <= d(cutoff)).sort("CERT", "REPDTE").collect()
    feats = feature_names(a)
    fill = lambda x: x.select(feats).cast(pl.Float64).fill_nan(None).fill_null(-9e9).to_numpy()  # noqa: E731
    assert a.height == b.height
    diff = fill(a) != fill(b)
    n = int(diff.sum())
    assert n == 0, f"{n} past feature values changed when future data changed -> leakage"
    return len(feats)


def main() -> None:
    panel = pl.read_parquet(PROC / "panel.parquet")
    n_feats = point_in_time_test(panel)
    print(f"point-in-time test passed on {n_feats} features")

    ft = (build_features(panel.lazy())
          .filter(pl.col("label_complete"))
          .with_columns(split_expr().alias("split"))
          # joins do not keep row order in Polars 2; HistGradientBoosting bins on a row
          # subsample, so a fixed order is needed for identical results on every rerun
          .sort("CERT", "REPDTE")
          .collect())
    feats = feature_names(ft)
    keep = ["CERT", "REPDTE", "q", "STNAME", "y", "split", "ASSET", "_next_fail_date", *feats]
    ft.select(keep).write_parquet(PROC / "features.parquet", compression="zstd")

    split = (ft.group_by("split").agg(
        pl.col("REPDTE").min().alias("from"), pl.col("REPDTE").max().alias("to"),
        pl.len().alias("bank-quarters"), pl.col("y").sum().alias("positive rows"),
        pl.col("CERT").filter(pl.col("y") == 1).n_unique().alias("failed banks"),
        (pl.col("y").mean() * 100).round(3).alias("positive %")).sort("from"))
    save_md(split, OUT / "p4_split.md", f"Time split (labels complete up to {LAST_MODEL_Q})")

    dev = ft.filter(pl.col("split") == "dev")
    desc = pl.DataFrame({
        "feature": feats,
        "group": [f.split("_")[0] for f in feats],
        "missing % (dev)": [round(dev[f].null_count() / dev.height * 100, 1) for f in feats],
        "median failed (dev)": [dev.filter(pl.col("y") == 1)[f].median() for f in feats],
        "median non-failed (dev)": [dev.filter(pl.col("y") == 0)[f].median() for f in feats],
    }).with_columns(pl.col(pl.Float64).round(3))
    save_md(desc, OUT / "p4_feature_table.md", "Features: missingness and failed vs non-failed medians (dev only)")
    (OUT / "p4_meta.json").write_text(json.dumps({"features": feats, "dev_end": DEV_END, "test_start": TEST_START}))
    print(split)


if __name__ == "__main__":
    main()

"""Try the early-warning model (the HGB chosen in Part 5, trained on the development period only).

    python src/predict.py                 # 20 riskiest banks in the latest quarter (2026Q2)
    python src/predict.py --cert 31027    # risk-score history of one bank
Scores from 2010 on are out-of-sample (the model never saw those years).
"""
from __future__ import annotations

import argparse
import json

import joblib
import polars as pl

from common import LAKE, OUT, PROC, ROOT
from features import build_features
from p5_model import hgb

MODEL = ROOT / "models" / "hgb_dev.joblib"
SHOW = ["CERT", "NAME", "STNAME", "REPDTE", "ASSET", "cap_eq_ta", "aq_noncurrent", "earn_roa", "risk_%", "alarm"]


def load_model(feats: list[str]):
    if MODEL.exists():
        return joblib.load(MODEL)
    ft = pl.read_parquet(PROC / "features.parquet").filter(pl.col("split") == "dev")
    model = hgb(0.05, 15).fit(ft.select(feats).to_numpy(), ft["y"].to_numpy())
    MODEL.parent.mkdir(exist_ok=True)
    joblib.dump(model, MODEL)
    return model


def threshold() -> float:
    """Base-case alarm threshold chosen on dev (outputs/p5_threshold_dev.md, cost ratio 0.01)."""
    row = [ln for ln in (OUT / "p5_threshold_dev.md").read_text(encoding="utf-8").splitlines()
           if ln.startswith("| HGB") and "| 0.01 " in ln][0]
    return float(row.split("|")[3])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cert", type=int)
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()

    feats = json.loads((OUT / "p4_meta.json").read_text())["features"]
    model = load_model(feats)
    t = threshold()
    # peer ranks / state shares need every bank of the quarter -> build on all, filter after
    f = build_features(pl.scan_parquet(PROC / "panel.parquet")).collect()
    f = f.filter(pl.col("CERT") == a.cert) if a.cert else f.filter(pl.col("REPDTE") == f["REPDTE"].max())
    names = pl.read_parquet(LAKE / "institutions.parquet").select("CERT", "NAME")
    s = model.predict_proba(f.select(feats).to_numpy())[:, 1]
    res = (f.with_columns(pl.Series("risk_%", s * 100).round(2), pl.Series("alarm", s >= t))
           .join(names, on="CERT", how="left")
           .with_columns((pl.col("ASSET") / 1e6).round(2).alias("ASSET"),   # $ billion
                         pl.col("cap_eq_ta", "aq_noncurrent", "earn_roa").round(2)))
    res = res.sort("REPDTE") if a.cert else res.sort("risk_%", descending=True).head(a.top)
    with pl.Config(tbl_rows=200, tbl_cols=20, tbl_width_chars=200, fmt_str_lengths=30):
        print(f"alarm threshold = {t*100:.2f}%  (ASSET in $ billion, ratios in %)")
        print(res.select(SHOW))


if __name__ == "__main__":
    main()

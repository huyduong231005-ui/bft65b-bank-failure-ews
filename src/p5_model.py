"""Part 5 - baseline vs own model, time-ordered validation, cost-based threshold, single test.

Run:  python src/p5_model.py        (needs p4_features.py first)
Out:  outputs/p5_*.md, outputs/p5_pr_curve.png

All choices (model, hyper-parameters, features, threshold) use the development period only.
The test period is scored exactly once, at the end of main().
"""
from __future__ import annotations

import json
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, precision_recall_curve, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import LAKE, OUT, PROC, SEED, save_md

BASELINE = ["cap_eq_ta", "aq_noncurrent", "earn_roa", "aq_ore_ta", "liq_brokered_dep", "size_log_assets"]
# expanding-window folds inside dev; 4-quarter purge gap between train end and validation start
FOLDS = [("1989-12-31", "1991-03-31", "1992-12-31"),
         ("1993-12-31", "1995-03-31", "1999-12-31"),
         ("2001-12-31", "2003-03-31", "2008-12-31")]
TOP_SHARE = 0.05          # supervisors can examine the riskiest 5% of banks each quarter
FP_COST_GRID = [0.005, 0.01, 0.02, 0.05]   # false-alarm cost as share of a missed failure's loss
FP_COST_BASE = 0.01


class Winsorizer(BaseEstimator, TransformerMixin):
    """Clip each column at quantiles learned on the training data only."""

    def __init__(self, q: float = 0.01):
        self.q = q

    def fit(self, X, y=None):
        self.lo_, self.hi_ = np.nanquantile(X, self.q, axis=0), np.nanquantile(X, 1 - self.q, axis=0)
        return self

    def transform(self, X):
        return np.clip(X, self.lo_, self.hi_)


class DropEmpty(BaseEstimator, TransformerMixin):
    """Drop columns that are entirely missing in the training data (e.g. P3ASSET before 2001)."""

    def fit(self, X, y=None):
        self.keep_ = ~np.isnan(X).all(axis=0)
        return self

    def transform(self, X):
        return X[:, self.keep_]


def logit():
    return make_pipeline(DropEmpty(), Winsorizer(), SimpleImputer(strategy="median", add_indicator=True),
                         StandardScaler(), LogisticRegression(C=0.1, class_weight="balanced", max_iter=2000))


def hgb(lr=0.05, leaves=15, l2=1.0):
    return make_pipeline(DropEmpty(), HistGradientBoostingClassifier(
        learning_rate=lr, max_leaf_nodes=leaves, l2_regularization=l2,
        max_iter=300, early_stopping=False, random_state=SEED))


def recall_at_top(df: pl.DataFrame, score: np.ndarray) -> float:
    """Share of failing bank-quarters inside the top TOP_SHARE of scores of their quarter."""
    r = (df.select("REPDTE", "y").with_columns(pl.Series("s", score))
         .with_columns((pl.col("s").rank("ordinal", descending=True).over("REPDTE")
                        <= (pl.len().over("REPDTE") * TOP_SHARE).ceil()).alias("flag")))
    return r.filter(pl.col("y") == 1)["flag"].mean()


def metrics(df: pl.DataFrame, score: np.ndarray) -> dict:
    y = df["y"].to_numpy()
    return {"PR-AUC": average_precision_score(y, score), "ROC-AUC": roc_auc_score(y, score),
            f"recall@top{int(TOP_SHARE*100)}%": recall_at_top(df, score), "Brier": brier_score_loss(y, score)}


def cv(dev: pl.DataFrame, feats: list[str], make) -> tuple[dict, pl.DataFrame]:
    oof = []
    for tr_end, va_start, va_end in FOLDS:
        tr = dev.filter(pl.col("REPDTE") <= pl.lit(tr_end).str.to_date())
        va = dev.filter(pl.col("REPDTE").is_between(pl.lit(va_start).str.to_date(), pl.lit(va_end).str.to_date()))
        m = make().fit(tr.select(feats).to_numpy(), tr["y"].to_numpy())
        oof.append(va.select("REPDTE", "CERT", "y", "ASSET").with_columns(
            pl.Series("s", m.predict_proba(va.select(feats).to_numpy())[:, 1])))
    oof = pl.concat(oof)
    return metrics(oof, oof["s"].to_numpy()), oof


def loss_given_failure() -> dict:
    """Missed-failure cost estimated from the data: DIF loss (COST) of dev-period failures."""
    f = (pl.read_parquet(LAKE / "failures.parquet")
         .filter((pl.col("RESTYPE") == "FAILURE") & pl.col("FAILDATE").is_between(pl.date(1984, 1, 1), pl.date(2009, 12, 31)))
         .filter(pl.col("COST").is_not_null() & (pl.col("QBFASSET") > 0)))
    return {"failures with cost": f.height, "median COST $k": float(f["COST"].median()),
            "median loss rate % of assets": float((f["COST"] / f["QBFASSET"] * 100).median())}


def choose_threshold(oof: pl.DataFrame, fp_cost: float) -> tuple[float, float]:
    """Minimise expected cost: missed failure = 1 (normalised loss), false alarm = fp_cost."""
    y, s = oof["y"].to_numpy(), oof["s"].to_numpy()
    grid = np.unique(np.quantile(s, np.linspace(0.5, 0.9999, 600)))
    costs = [((s < t) & (y == 1)).sum() + fp_cost * ((s >= t) & (y == 0)).sum() for t in grid]
    i = int(np.argmin(costs))
    return float(grid[i]), float(costs[i])


def confusion(y: np.ndarray, s: np.ndarray, t: float, fp_cost: float) -> dict:
    tp, fp = int(((s >= t) & (y == 1)).sum()), int(((s >= t) & (y == 0)).sum())
    fn = int(((s < t) & (y == 1)).sum())
    return {"threshold": t, "alarms": tp + fp, "TP": tp, "FP": fp, "FN": fn,
            "recall": tp / max(tp + fn, 1), "precision": tp / max(tp + fp, 1),
            "cost (missed=1)": fn + fp_cost * fp}


def main() -> None:
    meta = json.loads((OUT / "p4_meta.json").read_text())
    feats = meta["features"]
    ft = pl.read_parquet(PROC / "features.parquet")
    dev, test = ft.filter(pl.col("split") == "dev"), ft.filter(pl.col("split") == "test")

    # ---------------- model selection on dev only
    cands = {"baseline logit (6 CAMELS ratios)": (BASELINE, logit),
             "logit, all features": (feats, logit),
             **{f"HGB lr={lr} leaves={lv}": (feats, lambda lr=lr, lv=lv: hgb(lr, lv))
                for lr in (0.05, 0.1) for lv in (15, 31)}}
    rows, oofs = [], {}
    for name, (fs, make) in cands.items():
        m, oofs[name] = cv(dev, fs, make)
        rows.append({"model": name, "n_features": len(fs), **m})
        print(rows[-1])
    sel = pl.DataFrame(rows).with_columns(pl.col(pl.Float64).round(4))
    save_md(sel, OUT / "p5_cv.md", "Expanding-window CV on development period (pooled out-of-fold)")
    hgb_rows = sel.filter(pl.col("model").str.starts_with("HGB")).sort("PR-AUC", descending=True)
    best = hgb_rows["model"][0]

    # ---------------- cost-based threshold from out-of-fold dev predictions
    lgf = loss_given_failure()
    thr = {}
    sens = []
    for name in ("baseline logit (6 CAMELS ratios)", best):
        for c in FP_COST_GRID:
            t, _ = choose_threshold(oofs[name], c)
            thr[(name, c)] = t
            sens.append({"model": name, "false-alarm cost / missed-failure loss": c,
                         **confusion(oofs[name]["y"].to_numpy(), oofs[name]["s"].to_numpy(), t, c)})
    save_md(pl.DataFrame(sens).with_columns(pl.col(pl.Float64).round(4)), OUT / "p5_threshold_dev.md",
            f"Threshold chosen on dev OOF predictions. Loss given failure from data: {lgf}")

    # ---------------- single evaluation on the test period
    final, res = {}, []
    for name in ("baseline logit (6 CAMELS ratios)", best):
        fs, make = cands[name]
        model = make().fit(dev.select(fs).to_numpy(), dev["y"].to_numpy())
        s = model.predict_proba(test.select(fs).to_numpy())[:, 1]
        final[name] = s
        res.append({"model": name, **metrics(test, s),
                    **confusion(test["y"].to_numpy(), s, thr[(name, FP_COST_BASE)], FP_COST_BASE)})
    out = pl.DataFrame(res).with_columns(pl.col(pl.Float64).round(4))
    save_md(out, OUT / "p5_test_once.md",
            f"TEST period {test['REPDTE'].min()} - {test['REPDTE'].max()}, scored once at {datetime.now():%Y-%m-%d %H:%M}"
            f" (false-alarm cost = {FP_COST_BASE} x missed failure)")
    print(out)

    fig, ax = plt.subplots(figsize=(5, 4))
    for name, s in final.items():
        p, r, _ = precision_recall_curve(test["y"].to_numpy(), s)
        ax.plot(r, p, label=name)
    ax.axhline(test["y"].mean(), ls=":", c="grey", label="no skill")
    ax.set(xlabel="recall", ylabel="precision", title="Test period precision-recall")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(OUT / "p5_pr_curve.png", dpi=150)


if __name__ == "__main__":
    main()

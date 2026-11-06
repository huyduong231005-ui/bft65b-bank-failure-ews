"""Try the early-warning model (the HGB chosen in Part 5, trained on the development period only).

    python src/predict.py                 # 20 riskiest banks in the latest quarter (2026Q2)
    python src/predict.py --cert 31027    # risk-score history of one bank (+ chart)
    python src/predict.py --cert 1252 24735 628   # several banks, one line each on the chart
Scores from 2009 on are out-of-sample (the model never saw those years).
The chart is saved to outputs/risk_<certs>.png and opened.
"""
from __future__ import annotations

import argparse
import json
import os

import joblib
import matplotlib
import polars as pl

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

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


PAL = ["#D55E00", "#0072B2", "#009E73", "#E69F00", "#CC79A7", "#56B4E9", "#000000"]  # Okabe-Ito
STYLES = ["-", "--", "-.", ":"]


def plot(res: pl.DataFrame, t: float, certs: list[int]):
    """One line per bank: risk score over time, failure dates, alarm threshold, out-of-sample shading."""
    fails = (pl.read_parquet(LAKE / "failures.parquet").filter(pl.col("RESTYPE") == "FAILURE")
             .group_by("CERT").agg(pl.col("FAILDATE").max()))
    dev_end = json.loads((OUT / "p4_meta.json").read_text())["dev_end"]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.axvspan(pl.Series([dev_end]).str.to_date()[0], res["REPDTE"].max(), color="0.93", zorder=0,
               label="ngoài mẫu train (mô hình chưa thấy)")
    ax.axhline(t * 100, color="0.35", lw=1, ls=":", label=f"ngưỡng cảnh báo {t*100:.2f}%")
    for i, cert in enumerate(certs):
        d = res.filter(pl.col("CERT") == cert).sort("REPDTE")
        if d.is_empty():
            print(f"CERT {cert}: không có trong dữ liệu")
            continue
        col, ls = PAL[i % len(PAL)], STYLES[i % len(STYLES)]
        fd = fails.filter(pl.col("CERT") == cert)["FAILDATE"]
        label = f"{d['NAME'][0]} (CERT {cert}"
        label += f", phá sản {fd[0]:%d/%m/%Y})" if len(fd) else ", chưa phá sản)"
        ax.plot(d["REPDTE"], d["risk_raw"].clip(0.005, None), ls=ls, marker="o", ms=2.5, lw=1.6,
                color=col, label=label)
        if len(fd):
            ax.axvline(fd[0], color=col, lw=1, ls=ls)
    ax.set_yscale("log")
    ax.set_ylabel("điểm rủi ro, % (thang log)")
    ax.set_title("Điểm rủi ro phá sản trong 12 tháng tới, theo quý")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout()
    path = OUT / f"risk_{'_'.join(map(str, certs))}.png"
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cert", type=int, nargs="+", help="one or more CERT codes")
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()

    feats = json.loads((OUT / "p4_meta.json").read_text())["features"]
    model = load_model(feats)
    t = threshold()
    # peer ranks / state shares need every bank of the quarter -> build on all, filter after
    f = build_features(pl.scan_parquet(PROC / "panel.parquet")).collect()
    f = f.filter(pl.col("CERT").is_in(a.cert)) if a.cert else f.filter(pl.col("REPDTE") == f["REPDTE"].max())
    names = pl.read_parquet(LAKE / "institutions.parquet").select("CERT", "NAME")
    s = model.predict_proba(f.select(feats).to_numpy())[:, 1]
    res = (f.with_columns(pl.Series("risk_%", s * 100).round(2), pl.Series("risk_raw", s * 100),
                          pl.Series("alarm", s >= t))
           .join(names, on="CERT", how="left")
           .with_columns((pl.col("ASSET") / 1e6).round(2).alias("ASSET"),   # $ billion
                         pl.col("cap_eq_ta", "aq_noncurrent", "earn_roa").round(2)))
    res = res.sort("CERT", "REPDTE") if a.cert else res.sort("risk_%", descending=True).head(a.top)
    with pl.Config(tbl_rows=1000, tbl_cols=20, tbl_width_chars=200, fmt_str_lengths=30):
        print(f"alarm threshold = {t*100:.2f}%  (ASSET in $ billion, ratios in %)")
        print(res.select(SHOW))
    if a.cert:
        path = plot(res, t, a.cert)
        print(f"chart saved: {path}")
        if hasattr(os, "startfile"):
            os.startfile(path)  # ponytail: Windows only; elsewhere just open the saved PNG


if __name__ == "__main__":
    main()

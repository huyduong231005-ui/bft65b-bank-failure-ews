"""Point-in-time CAMELS feature builder (Polars lazy). Used by Part 3 (benchmark) and Part 4.

Every feature for row (bank i, quarter q) uses only reports with REPDTE <= q:
  * ratios from the current report,
  * lags joined on the exact quarter index q-k (a missing quarter gives null, never an older report),
  * cross-sectional peer ranks/state shares computed within the same quarter.
"""
from __future__ import annotations

import polars as pl


def ratio(num: pl.Expr, den: pl.Expr) -> pl.Expr:
    """num/den in %, null when the denominator is not positive."""
    return pl.when(den > 0).then(num / den * 100).otherwise(None)


RATIOS: dict[str, pl.Expr] = {
    # C - capital
    "cap_eq_ta": ratio(pl.col("EQ"), pl.col("ASSET")),
    "cap_t1_lev": pl.col("RBC1AAJ"),
    "cap_rbc": pl.col("RBCRWAJ"),
    # A - asset quality
    "aq_noncurrent": ratio(pl.col("NCLNLS"), pl.col("LNLSGR")),
    "aq_pd30_ta": ratio(pl.col("P3ASSET"), pl.col("ASSET")),
    "aq_pd90_ta": ratio(pl.col("P9ASSET"), pl.col("ASSET")),
    "aq_nonaccr_ta": ratio(pl.col("NAASSET"), pl.col("ASSET")),
    "aq_nco": ratio(pl.col("NTLNLS"), pl.col("LNLSGR")),
    "aq_ore_ta": ratio(pl.col("ORE"), pl.col("ASSET")),
    "aq_alll": ratio(pl.col("LNATRES"), pl.col("LNLSGR")),
    "aq_texas": ratio(pl.col("NCLNLS") + pl.col("ORE").fill_null(0),
                      pl.col("EQ") + pl.col("LNATRES").fill_null(0)),
    # M / E - management efficiency, earnings (flows already annualised in the panel)
    "earn_roa": ratio(pl.col("NETINC"), pl.col("ASSET")),
    "earn_nim": pl.col("NIMY"),
    "earn_prov_ta": ratio(pl.col("ELNATR"), pl.col("ASSET")),
    "earn_yield_ta": ratio(pl.col("INTINC"), pl.col("ASSET")),
    "earn_cost_funds": ratio(pl.col("EINTEXP"), pl.col("LIAB")),
    "mgmt_efficiency": ratio(pl.col("NONIX"), pl.col("INTINC") - pl.col("EINTEXP") + pl.col("NONII")),
    # L - liquidity and funding
    "liq_liquid_ta": ratio(pl.col("CHBAL") + pl.col("SC"), pl.col("ASSET")),
    "liq_loans_dep": ratio(pl.col("LNLSNET"), pl.col("DEP")),
    "liq_brokered_dep": ratio(pl.col("BRO"), pl.col("DEP")),
    "liq_core_ta": ratio(pl.col("COREDEP"), pl.col("ASSET")),
    "liq_volatile_ta": ratio(pl.col("VOLIAB"), pl.col("ASSET")),
    "liq_wholesale_ta": ratio(pl.col("FREPP").fill_null(0) + pl.col("OTHBFHLB").fill_null(0), pl.col("ASSET")),
    # S - loan-book concentration (sensitivity), size
    "conc_re": ratio(pl.col("LNRE"), pl.col("LNLSGR")),
    "conc_ci": ratio(pl.col("LNCI"), pl.col("LNLSGR")),
    "conc_con": ratio(pl.col("LNCON"), pl.col("LNLSGR")),
    "size_log_assets": pl.col("ASSET").log(),
    "loans_ta": ratio(pl.col("LNLSGR"), pl.col("ASSET")),
}
CHANGE_OF = ["cap_eq_ta", "aq_noncurrent", "earn_roa", "liq_brokered_dep", "aq_alll"]
PEER_RANK_OF = ["cap_eq_ta", "aq_noncurrent", "earn_roa", "aq_texas"]
LAGGED_LEVELS = ["ASSET", "LNLSGR"]


def build_features(panel: pl.LazyFrame) -> pl.LazyFrame:
    base = panel.with_columns(**RATIOS)

    # exact-quarter self-join: q-4 (year-on-year) and q-1 (last quarter)
    lag_cols = [*CHANGE_OF, *LAGGED_LEVELS]
    lag4 = base.select("CERT", (pl.col("q") + 4).alias("q"), *[pl.col(c).alias(f"{c}__l4") for c in lag_cols])
    lag1 = base.select("CERT", (pl.col("q") + 1).alias("q"), pl.col("earn_roa").alias("earn_roa__l1"))
    f = (base.join(lag4, on=["CERT", "q"], how="left")
         .join(lag1, on=["CERT", "q"], how="left")
         .with_columns(
             *[(pl.col(c) - pl.col(f"{c}__l4")).alias(f"d4_{c}") for c in CHANGE_OF],
             ratio(pl.col("ASSET") - pl.col("ASSET__l4"), pl.col("ASSET__l4")).alias("g4_assets"),
             ratio(pl.col("LNLSGR") - pl.col("LNLSGR__l4"), pl.col("LNLSGR__l4")).alias("g4_loans"),
             (pl.col("earn_roa") - pl.col("earn_roa__l1")).alias("d1_earn_roa"),
             (pl.col("n_hist") < 12).cast(pl.Int8).alias("young_bank"),
         ))

    # peer context inside the same quarter (information everyone has at time q)
    f = f.with_columns(
        *[pl.col(c).rank("average").over("REPDTE").truediv(pl.col(c).count().over("REPDTE"))
          .alias(f"pr_{c}") for c in PEER_RANK_OF],
        (pl.col("earn_roa") < 0).mean().over("REPDTE", "STNAME").alias("state_share_loss"),
        pl.col("aq_noncurrent").median().over("REPDTE", "STNAME").alias("state_med_noncurrent"),
    )
    return f.drop([c for c in f.collect_schema().names() if c.endswith(("__l4", "__l1"))])


def feature_names(lf: pl.LazyFrame | pl.DataFrame) -> list[str]:
    prefixes = ("cap_", "aq_", "earn_", "mgmt_", "liq_", "conc_", "size_", "loans_",
                "d4_", "g4_", "d1_", "pr_", "state_", "young_")
    return [c for c in lf.collect_schema().names() if c.startswith(prefixes)]

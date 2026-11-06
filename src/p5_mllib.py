"""Part 5 - short Spark MLlib demo: the baseline logit as a Spark ML Pipeline, dev -> test.

Run:  python src/p5_mllib.py   (JAVA_HOME = JDK 17; needs p4_features.py)
Out:  outputs/p5_mllib.md
"""
from __future__ import annotations

import time

import polars as pl
from pyspark.ml import Pipeline
from pyspark.ml.classification import LogisticRegression
from pyspark.ml.evaluation import BinaryClassificationEvaluator
from pyspark.ml.feature import Imputer, StandardScaler, VectorAssembler
from pyspark.sql import functions as F

from common import OUT, PROC, get_spark, save_md
from p5_model import BASELINE


def main() -> None:
    spark = get_spark("p5-mllib")
    df = spark.read.parquet(str(PROC / "features.parquet")).select("split", "y", *BASELINE)
    dev, test = df.filter(F.col("split") == "dev"), df.filter(F.col("split") == "test")
    n_pos, n = dev.agg(F.sum("y"), F.count("*")).first()
    w = (n - n_pos) / n_pos   # 'balanced' class weight, like sklearn
    dev = dev.withColumn("w", F.when(F.col("y") == 1, F.lit(w)).otherwise(F.lit(1.0)))
    # winsorise at 1%/99% quantiles of the dev period (same as the sklearn pipeline)
    for c in BASELINE:
        lo, hi = dev.approxQuantile(c, [0.01, 0.99], 0.001)
        clip = lambda col, lo=lo, hi=hi: F.least(F.greatest(col, F.lit(lo)), F.lit(hi))  # noqa: E731
        dev, test = dev.withColumn(c, clip(F.col(c))), test.withColumn(c, clip(F.col(c)))

    imp = [f"{c}_i" for c in BASELINE]
    pipe = Pipeline(stages=[
        Imputer(inputCols=BASELINE, outputCols=imp, strategy="median"),   # medians fitted on dev only
        VectorAssembler(inputCols=imp, outputCol="raw"),
        StandardScaler(inputCol="raw", outputCol="features", withMean=True),
        LogisticRegression(labelCol="y", weightCol="w", regParam=0.01, maxIter=100),
    ])
    t0 = time.perf_counter()
    model = pipe.fit(dev)
    fit_s = time.perf_counter() - t0
    pred = model.transform(test)
    ev = BinaryClassificationEvaluator(labelCol="y", rawPredictionCol="rawPrediction")
    res = pl.DataFrame({
        "metric": ["fit seconds (local[*])", "test PR-AUC", "test ROC-AUC", "dev rows", "test rows"],
        "value": [round(fit_s, 1), round(ev.setMetricName("areaUnderPR").evaluate(pred), 4),
                  round(ev.setMetricName("areaUnderROC").evaluate(pred), 4), n, test.count()]})
    coef = pl.DataFrame({"feature": BASELINE, "coef (standardised)":
                         [round(float(c), 4) for c in model.stages[-1].coefficients]})
    save_md(res, OUT / "p5_mllib.md", "Spark MLlib baseline logit (dev -> test)")
    with open(OUT / "p5_mllib.md", "a", encoding="utf-8") as fh:
        fh.write("\n")
    save_md(coef, OUT / "_c.md", "Coefficients")
    (OUT / "p5_mllib.md").write_text((OUT / "p5_mllib.md").read_text(encoding="utf-8")
                                     + (OUT / "_c.md").read_text(encoding="utf-8"), encoding="utf-8")
    (OUT / "_c.md").unlink()
    print(res, coef)
    spark.stop()


if __name__ == "__main__":
    main()

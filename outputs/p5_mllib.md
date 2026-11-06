### Spark MLlib baseline logit (dev -> test)

| metric                 | value      |
|------------------------|------------|
| fit seconds (local[*]) | 9.8        |
| test PR-AUC            | 0.4913     |
| test ROC-AUC           | 0.98       |
| dev rows               | 1.262549e6 |
| test rows              | 368527.0   |

### Coefficients

| feature          | coef (standardised) |
|------------------|---------------------|
| cap_eq_ta        | -1.5205             |
| aq_noncurrent    | 0.4794              |
| earn_roa         | -0.488              |
| aq_ore_ta        | 0.2815              |
| liq_brokered_dep | 0.2555              |
| size_log_assets  | -0.0968             |

### Spark MLlib baseline logit (dev -> test)

| metric                 | value      |
|------------------------|------------|
| fit seconds (local[*]) | 10.6       |
| test PR-AUC            | 0.4908     |
| test ROC-AUC           | 0.9801     |
| dev rows               | 1.262549e6 |
| test rows              | 368527.0   |

### Coefficients

| feature          | coef (standardised) |
|------------------|---------------------|
| cap_eq_ta        | -1.5353             |
| aq_noncurrent    | 0.4783              |
| earn_roa         | -0.4862             |
| aq_ore_ta        | 0.2828              |
| liq_brokered_dep | 0.2555              |
| size_log_assets  | -0.0963             |

### Expanding-window CV on development period (pooled out-of-fold)

| model                            | n_features | PR-AUC | ROC-AUC | recall@top5% | Brier  |
|----------------------------------|------------|--------|---------|--------------|--------|
| baseline logit (6 CAMELS ratios) | 6          | 0.2361 | 0.9699  | 0.807        | 0.0147 |
| logit, all features              | 43         | 0.2474 | 0.9697  | 0.8142       | 0.0083 |
| HGB lr=0.05 leaves=15            | 43         | 0.434  | 0.9828  | 0.8387       | 0.0022 |
| HGB lr=0.05 leaves=31            | 43         | 0.4204 | 0.9821  | 0.8351       | 0.0022 |
| HGB lr=0.1 leaves=15             | 43         | 0.4092 | 0.9818  | 0.8268       | 0.0023 |
| HGB lr=0.1 leaves=31             | 43         | 0.3883 | 0.9805  | 0.8327       | 0.0023 |

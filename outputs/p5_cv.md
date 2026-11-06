### Expanding-window CV on development period (pooled out-of-fold)

| model                            | n_features | PR-AUC | ROC-AUC | recall@top5% | Brier  |
|----------------------------------|------------|--------|---------|--------------|--------|
| baseline logit (6 CAMELS ratios) | 6          | 0.2361 | 0.9699  | 0.807        | 0.0147 |
| logit, all features              | 43         | 0.2491 | 0.9703  | 0.8154       | 0.0084 |
| HGB lr=0.05 leaves=15            | 43         | 0.4225 | 0.9826  | 0.8417       | 0.0022 |
| HGB lr=0.05 leaves=31            | 43         | 0.4173 | 0.9826  | 0.8351       | 0.0022 |
| HGB lr=0.1 leaves=15             | 43         | 0.3977 | 0.9812  | 0.8303       | 0.0023 |
| HGB lr=0.1 leaves=31             | 43         | 0.3916 | 0.9807  | 0.8232       | 0.0023 |

### Threshold chosen on dev OOF predictions. Loss given failure from data: {'failures with cost': 2456, 'median COST $k': 9494.24237, 'median loss rate % of assets': 21.151285114127624}

| model                            | false-alarm cost / missed-failure loss | threshold | alarms | TP   | FP    | FN  | recall | precision | cost (missed=1) |
|----------------------------------|----------------------------------------|-----------|--------|------|-------|-----|--------|-----------|-----------------|
| baseline logit (6 CAMELS ratios) | 0.005                                  | 0.2744    | 19576  | 1476 | 18100 | 198 | 0.8817 | 0.0754    | 288.5           |
| baseline logit (6 CAMELS ratios) | 0.01                                   | 0.3125    | 16322  | 1452 | 14870 | 222 | 0.8674 | 0.089     | 370.7           |
| baseline logit (6 CAMELS ratios) | 0.02                                   | 0.5031    | 8422   | 1331 | 7091  | 343 | 0.7951 | 0.158     | 484.82          |
| baseline logit (6 CAMELS ratios) | 0.05                                   | 0.5466    | 7492   | 1303 | 6189  | 371 | 0.7784 | 0.1739    | 680.45          |
| HGB lr=0.05 leaves=15            | 0.005                                  | 0.0019    | 26547  | 1538 | 25009 | 136 | 0.9188 | 0.0579    | 261.045         |
| HGB lr=0.05 leaves=15            | 0.01                                   | 0.0045    | 15858  | 1469 | 14389 | 205 | 0.8775 | 0.0926    | 348.89          |
| HGB lr=0.05 leaves=15            | 0.02                                   | 0.011     | 9816   | 1386 | 8430  | 288 | 0.828  | 0.1412    | 456.6           |
| HGB lr=0.05 leaves=15            | 0.05                                   | 0.0285    | 6098   | 1273 | 4825  | 401 | 0.7605 | 0.2088    | 642.25          |

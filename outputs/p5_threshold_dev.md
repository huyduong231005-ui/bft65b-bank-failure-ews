### Threshold chosen on dev OOF predictions. Loss given failure from data: {'failures with cost': 2316, 'median COST $k': 8381.673354999999, 'median loss rate % of assets': 20.776232881194574}

| model                            | false-alarm cost / missed-failure loss | threshold | alarms | TP   | FP    | FN  | recall | precision | cost (missed=1) |
|----------------------------------|----------------------------------------|-----------|--------|------|-------|-----|--------|-----------|-----------------|
| baseline logit (6 CAMELS ratios) | 0.005                                  | 0.2744    | 19576  | 1476 | 18100 | 198 | 0.8817 | 0.0754    | 288.5           |
| baseline logit (6 CAMELS ratios) | 0.01                                   | 0.3125    | 16322  | 1452 | 14870 | 222 | 0.8674 | 0.089     | 370.7           |
| baseline logit (6 CAMELS ratios) | 0.02                                   | 0.5031    | 8422   | 1331 | 7091  | 343 | 0.7951 | 0.158     | 484.82          |
| baseline logit (6 CAMELS ratios) | 0.05                                   | 0.5466    | 7492   | 1303 | 6189  | 371 | 0.7784 | 0.1739    | 680.45          |
| HGB lr=0.05 leaves=15            | 0.005                                  | 0.002     | 25617  | 1546 | 24071 | 128 | 0.9235 | 0.0604    | 248.355         |
| HGB lr=0.05 leaves=15            | 0.01                                   | 0.0055    | 13999  | 1448 | 12551 | 226 | 0.865  | 0.1034    | 351.51          |
| HGB lr=0.05 leaves=15            | 0.02                                   | 0.0099    | 10281  | 1395 | 8886  | 279 | 0.8333 | 0.1357    | 456.72          |
| HGB lr=0.05 leaves=15            | 0.05                                   | 0.04      | 5168   | 1228 | 3940  | 446 | 0.7336 | 0.2376    | 643.0           |

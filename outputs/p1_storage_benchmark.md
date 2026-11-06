### Storage layouts, 1,682,616 rows x 39 cols (median of 3 runs)

| layout                                 | size_MB | write_s | read_all_s | read_3_cols_s | filter_2008_s | size_vs_csv | filter_speedup_vs_csv |
|----------------------------------------|---------|---------|------------|---------------|---------------|-------------|-----------------------|
| CSV (raw text)                         | 486.0   | 0.425   | 0.576      | 0.251         | 0.24          | 1.0         | 1.0                   |
| CSV + gzip                             | 186.0   | 34.79   | 1.072      | 0.999         | 0.916         | 0.383       | 0.3                   |
| Parquet snappy, 1 file                 | 229.5   | 0.233   | 0.175      | 0.009         | 0.008         | 0.472       | 30.0                  |
| Parquet zstd, 1 file                   | 161.0   | 0.49    | 0.225      | 0.01          | 0.015         | 0.331       | 16.0                  |
| Parquet zstd, YEAR partitions (chosen) | 168.5   | null    | 0.183      | 0.018         | 0.013         | 0.347       | 18.5                  |

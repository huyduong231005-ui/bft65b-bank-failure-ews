# Automated data-quality report

### Panel construction summary

| metric                                       | value   |
|----------------------------------------------|---------|
| raw panel rows                               | 1682616 |
| rows dropped: ASSET <= 0 / null              | 0       |
| rows dropped: on/after failure               | 1095    |
| clean panel rows                             | 1681521 |
| rows with complete label (<= 2025Q2)         | 1663992 |
| positive rows (y=1)                          | 10860   |
| failed banks with >=1 positive row           | 2837    |
| CERTs with several failure/assistance events | 45      |

### Bank exits (treated separately)

| _exit_type                                       | banks |
|--------------------------------------------------|-------|
| active                                           | 4313  |
| failure                                          | 2837  |
| other exit (merger, liquidation, charter change) | 16914 |

### Failures table by resolution type (1984+)

| RESTYPE    | events | COST missing |
|------------|--------|--------------|
| ASSISTANCE | 412    | 19           |
| FAILURE    | 2863   | 23           |

### Failure coverage in Financials (RESTYPE=FAILURE, 1984+)

| case                            | failures | also report after failure |
|---------------------------------|----------|---------------------------|
| last report 1 quarter before    | 2507     | 271                       |
| last report 2-4 quarters before | 333      | 0                         |
| not in Financials               | 21       | 0                         |

### Value / consistency checks on raw panel

| check                                                    | rows   | % of rows |
|----------------------------------------------------------|--------|-----------|
| duplicate CERT-REPDTE                                    | 0      | 0.0       |
| ASSET <= 0 or null                                       | 0      | 0.0       |
| EQ > ASSET                                               | 1      | 0.0       |
| EQ < 0 (insolvent book equity)                           | 15659  | 0.931     |
| |ASSET - LIAB - EQ| > 1% of ASSET                        | 1039   | 0.062     |
| negative stock (DEP, LNLSGR, NCLNLS, SC, CHBAL, LNATRES) | 141    | 0.008     |
| LNLSGR > ASSET                                           | 761    | 0.045     |
| |ROA| > 20%                                              | 5554   | 0.33      |
| |ROE| > 200%                                             | 4624   | 0.275     |
| ROE null while ROA present                               | 18743  | 1.114     |
| RBC1AAJ > 100 or < -100                                  | 2969   | 0.176     |
| RBC1AAJ == 0 while EQ > 0 (zero = not reported)          | 64335  | 3.824     |
| RBCRWAJ == 0 while EQ > 0 (zero = not reported)          | 451842 | 26.854    |
| tiny bank (ASSET < $5m)                                  | 14363  | 0.854     |

### Reporting gaps

| metric                                              | value |
|-----------------------------------------------------|-------|
| banks                                               | 24064 |
| banks with >=1 missing quarter inside their history | 32    |
| missing bank-quarters inside histories              | 92    |
| banks with < 4 quarters of history                  | 771   |

### Schema drift between raw quarterly files

| column  | raw dtypes      | n_dtypes |
|---------|-----------------|----------|
| CHBAL   | Float64 / Int64 | 2        |
| COREDEP | Float64 / Int64 | 2        |
| DEP     | Float64 / Int64 | 2        |
| DEPDOM  | Float64 / Int64 | 2        |
| LIAB    | Float64 / Int64 | 2        |
| LNCI    | Float64 / Int64 | 2        |
| LNCON   | Float64 / Int64 | 2        |
| LNLSGR  | Float64 / Int64 | 2        |
| LNLSNET | Float64 / Int64 | 2        |
| LNRE    | Float64 / Int64 | 2        |
| NAASSET | Float64 / Int64 | 2        |
| NCLNLS  | Float64 / Int64 | 2        |
| P3ASSET | Int64 / Null    | 2        |
| P9ASSET | Float64 / Int64 | 2        |
| RBCRWAJ | Float64 / Int64 | 2        |
| SC      | Float64 / Int64 | 2        |

### YTD reporting of income items

| quarter_of_year | median NETINC/ASSET % | median INTINC/ASSET % | median ROA % (already annualised) |
|-----------------|-----------------------|-----------------------|-----------------------------------|
| 1               | 0.242                 | 1.771                 | 0.971                             |
| 2               | 0.494                 | 3.524                 | 0.989                             |
| 3               | 0.729                 | 5.262                 | 0.993                             |
| 4               | 0.909                 | 6.888                 | 0.944                             |

### Missing % by era

| era       | ASSET | DEP | DEPDOM | EQ  | BRO | CHBAL | SC  | LNLSGR | LNLSNET | LNRE | LNCI | LNCON | LNATRES | NCLNLS | P3ASSET | P9ASSET | NAASSET | NTLNLS | ORE | NETINC | INTINC | EINTEXP | NONII | NONIX | ELNATR | ROA | ROE | NIMY | RBC1AAJ | RBCRWAJ | LIAB | COREDEP | VOLIAB | FREPP | OTHBFHLB | NUMEMP |
|-----------|-------|-----|--------|-----|-----|-------|-----|--------|---------|------|------|-------|---------|--------|---------|---------|---------|--------|-----|--------|--------|---------|-------|-------|--------|-----|-----|------|---------|---------|------|---------|--------|-------|----------|--------|
| 1984-89   | 0.0   | 0.0 | 0.0    | 0.2 | 3.2 | 0.0   | 0.0 | 0.0    | 0.0     | 0.0  | 0.0  | 0.1   | 0.2     | 0.6    | 100.0   | 18.5    | 18.5    | 18.3   | 0.2 | 0.3    | 0.3    | 0.7     | 0.3   | 0.3   | 9.5    | 0.0 | 3.0 | 0.0  | 0.0     | 0.0     | 0.0  | 0.0     | 0.2    | 0.0   | 82.1     | 18.3   |
| 1990-2000 | 0.0   | 0.0 | 0.0    | 0.3 | 0.3 | 0.0   | 0.0 | 0.0    | 0.0     | 0.0  | 0.0  | 0.3   | 0.3     | 0.0    | 100.0   | 0.0     | 0.0     | 0.3    | 0.3 | 0.3    | 0.3    | 0.3     | 0.3   | 0.3   | 0.3    | 0.0 | 0.8 | 0.0  | 0.0     | 0.0     | 0.0  | 0.0     | 0.3    | 0.0   | 87.0     | 0.3    |
| 2001-10   | 0.0   | 0.0 | 0.0    | 0.2 | 0.2 | 0.0   | 0.0 | 0.0    | 0.0     | 0.0  | 0.0  | 0.2   | 0.2     | 0.0    | 0.0     | 0.0     | 0.0     | 0.2    | 0.2 | 0.2    | 0.2    | 0.2     | 0.2   | 0.2   | 0.2    | 0.0 | 0.2 | 0.0  | 0.0     | 0.0     | 0.0  | 0.0     | 0.2    | 0.0   | 0.2      | 0.2    |
| 2011-26   | 0.0   | 0.0 | 0.0    | 0.3 | 0.3 | 0.0   | 0.0 | 0.0    | 0.0     | 0.0  | 0.0  | 0.3   | 0.3     | 0.0    | 0.0     | 0.0     | 0.0     | 0.3    | 0.3 | 0.3    | 0.3    | 0.3     | 0.3   | 0.3   | 0.3    | 0.0 | 0.3 | 0.0  | 0.0     | 0.0     | 0.0  | 0.3     | 0.3    | 0.0   | 0.3      | 0.3    |

### Exact-zero % by period (zero used as 'not reported')

| from year | RBC1AAJ | RBCRWAJ | BRO  | FREPP | P9ASSET | NAASSET | COREDEP | VOLIAB |
|-----------|---------|---------|------|-------|---------|---------|---------|--------|
| 1980      | 17.7    | 100.0   | 95.6 | 66.5  | 10.3    | 33.9    | 0.2     | 3.8    |
| 1985      | 18.2    | 100.0   | 91.3 | 72.6  | 13.7    | 20.3    | 0.4     | 2.5    |
| 1990      | 0.3     | 0.3     | 91.5 | 70.7  | 24.3    | 18.7    | 0.6     | 1.7    |
| 1995      | 0.3     | 0.3     | 87.9 | 65.7  | 27.9    | 22.7    | 1.0     | 1.5    |
| 2000      | 0.2     | 0.2     | 80.4 | 63.9  | 34.0    | 23.3    | 1.6     | 1.6    |
| 2005      | 0.2     | 0.2     | 62.0 | 61.4  | 40.8    | 21.1    | 1.4     | 1.6    |
| 2010      | 0.2     | 0.2     | 59.7 | 68.6  | 47.9    | 12.2    | 1.2     | 5.1    |
| 2015      | 0.3     | 0.3     | 58.5 | 71.1  | 51.2    | 15.2    | 1.2     | 4.2    |
| 2020      | 0.4     | 36.4    | 61.0 | 77.6  | 55.5    | 19.8    | 1.3     | 3.4    |
| 2025      | 0.4     | 39.8    | 53.7 | 80.8  | 54.2    | 19.0    | 1.6     | 2.8    |

### CHANGEC1 codes by derived exit type (top 5)

| _exit_type                                       | CHANGEC1 | len   |
|--------------------------------------------------|----------|-------|
| active                                           | null     | 3521  |
| active                                           | 810      | 300   |
| active                                           | 520      | 202   |
| active                                           | 510      | 109   |
| active                                           | 820      | 52    |
| failure                                          | 211      | 2374  |
| failure                                          | 230      | 180   |
| failure                                          | 217      | 159   |
| failure                                          | 213      | 95    |
| failure                                          | 235      | 25    |
| other exit (merger, liquidation, charter change) | 223      | 14183 |
| other exit (merger, liquidation, charter change) | 221      | 807   |
| other exit (merger, liquidation, charter change) | 240      | 504   |
| other exit (merger, liquidation, charter change) | 217      | 488   |
| other exit (merger, liquidation, charter change) | 213      | 242   |

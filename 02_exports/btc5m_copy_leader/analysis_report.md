# Copy-trade leader search

Generated 2026-06-11T12:40:59Z. 627 bot-fee-paying follower
wallets; 12891 follower BUY events across
1786 cached markets (final ~300s windows, May-Jun + partial
Jan-Apr). Candidate = wallet trading same market+direction 1-
3s before a follower event.

Leader signature = high lead_ratio (asymmetry), many distinct followers,
high conversion_rate (share of its own trades that get mirrored).
Symmetric high-volume wallets are market makers, not leaders. Candidates
that are themselves followers are fast mirrors of the true signal.

## Candidates with >= 5 distinct followers and lead_ratio >= 0.6

| wallet | follower? | watch | leads | lags | ratio | followers | markets | own trades | conversion |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0x218f36c313…` | 0 | - | 1331 | 797 | 0.63 | 80 | 409 | 23917 | 0.06 |
| `0x1f19c48aee…` | 0 | - | 1084 | 636 | 0.63 | 78 | 388 | 20776 | 0.05 |
| `0x60889af507…` | 0 | - | 1044 | 637 | 0.62 | 75 | 331 | 15472 | 0.07 |
| `0xe0229e10a8…` | 0 | - | 1144 | 686 | 0.63 | 71 | 307 | 23884 | 0.05 |
| `0xfda3e79ca1…` | 0 | - | 378 | 246 | 0.61 | 55 | 78 | 4032 | 0.09 |
| `0xd47cf8a429…` | 0 | - | 236 | 137 | 0.63 | 54 | 96 | 1867 | 0.13 |
| `0x674887d1ac…` | 0 | - | 569 | 294 | 0.66 | 53 | 288 | 8450 | 0.07 |
| `0x5d3cc45e53…` | 0 | - | 327 | 161 | 0.67 | 51 | 131 | 5064 | 0.06 |
| `0x510ae1a69e…` | 0 | - | 530 | 200 | 0.73 | 50 | 164 | 5556 | 0.10 |
| `0x19cd345dcd…` | 0 | - | 178 | 105 | 0.63 | 49 | 75 | 2954 | 0.06 |
| `0x75cc3b63a2…` | 0 | - | 380 | 184 | 0.67 | 48 | 201 | 6705 | 0.06 |
| `0x7399fe3ecd…` | 0 | - | 351 | 223 | 0.61 | 48 | 186 | 6109 | 0.06 |
| `0x12c2782b74…` | 0 | - | 549 | 354 | 0.61 | 47 | 48 | 436 | 1.26 |
| `0xe3575b1f6c…` | 0 | - | 347 | 203 | 0.63 | 47 | 196 | 8367 | 0.04 |
| `0x45e26c1913…` | 0 | - | 127 | 76 | 0.63 | 47 | 67 | 2722 | 0.05 |
| `0xf3531b23b5…` | 0 | - | 612 | 356 | 0.63 | 46 | 152 | 5065 | 0.12 |
| `0x0bba462910…` | 0 | - | 339 | 210 | 0.62 | 46 | 185 | 5941 | 0.06 |
| `0xf3234d1e60…` | 0 | - | 539 | 295 | 0.65 | 45 | 42 | 138 | 3.91 |
| `0x5a7816afd4…` | 0 | - | 298 | 190 | 0.61 | 45 | 123 | 3155 | 0.09 |
| `0x58eb15addb…` | 0 | - | 918 | 610 | 0.60 | 43 | 52 | 319 | 2.88 |
| `0x548254ca3e…` | 0 | - | 381 | 241 | 0.61 | 43 | 47 | 437 | 0.87 |
| `0xa6896d11f7…` | 0 | - | 347 | 173 | 0.67 | 43 | 163 | 3093 | 0.11 |
| `0x23f544a1f9…` | 0 | - | 274 | 158 | 0.63 | 43 | 48 | 264 | 1.04 |
| `0x2bc01f3ad8…` | 0 | - | 1207 | 335 | 0.78 | 42 | 53 | 222 | 5.44 |
| `0xa82365c8e8…` | 0 | - | 458 | 270 | 0.63 | 42 | 40 | 353 | 1.30 |

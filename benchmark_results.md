# Benchmark: MB-tree vs EMB-tree

- 10,000 records inserted in random order (seed 42); 1,000 reads, 200 range reads of 50 records, 1,000 updates
- times: microseconds per operation, median of 5 runs (the two trees take turns); proof generation = full read - lookup only
- timings move by tens of percent between runs on a laptop, so only large differences mean something; proof sizes are exact
- Python 3.14.0 on Windows-11-10.0.26300-SP0

## Fanout 8 (EMB-tree: f_e = 8, f_k = 2); tree height MB 6, EMB 6

| Measurement (µs per operation) | MB-tree | EMB-tree |
|---|---:|---:|
| Insert (per record) | 33.8 | 126.3 |
| Read: lookup only | 3.2 | 3.6 |
| Read: full read() incl. proof | 12.7 | 23.0 |
| Proof generation (read) | 9.5 | 18.7 |
| Verification (read) | 38.7 | 73.8 |
| Range read: lookup only | 24.1 | 23.8 |
| Range read: full read_range() incl. proof | 77.6 | 237.5 |
| Proof generation (range) | 53.6 | 213.7 |
| Verification (range) | 304.3 | 469.0 |
| Update | 37.4 | 64.6 |

| Proof size (average) | MB-tree | EMB-tree |
|---|---:|---:|
| read: hashes | 25.0 | 14.1 |
| read: hash bytes | 799 | 453 |
| read: total bytes incl. records | 822 | 476 |
| range (50 records + 2 boundary): hashes | 25.1 | 14.3 |
| range (50 records + 2 boundary): hash bytes | 802 | 456 |
| range (50 records + 2 boundary): total bytes incl. records | 1,993 | 1,648 |

Both trees gave identical answers; every proof was verified.

## Fanout 32 (EMB-tree: f_e = 32, f_k = 2); tree height MB 3, EMB 3

| Measurement (µs per operation) | MB-tree | EMB-tree |
|---|---:|---:|
| Insert (per record) | 32.6 | 206.3 |
| Read: lookup only | 2.2 | 2.3 |
| Read: full read() incl. proof | 10.0 | 18.2 |
| Proof generation (read) | 7.3 | 15.9 |
| Verification (read) | 47.8 | 69.3 |
| Range read: lookup only | 19.4 | 20.1 |
| Range read: full read_range() incl. proof | 59.3 | 157.9 |
| Proof generation (range) | 39.9 | 135.9 |
| Verification (range) | 296.2 | 456.0 |
| Update | 32.3 | 56.9 |

| Proof size (average) | MB-tree | EMB-tree |
|---|---:|---:|
| read: hashes | 64.3 | 14.2 |
| read: hash bytes | 2,056 | 455 |
| read: total bytes incl. records | 2,079 | 478 |
| range (50 records + 2 boundary): hashes | 63.5 | 14.2 |
| range (50 records + 2 boundary): hash bytes | 2,031 | 454 |
| range (50 records + 2 boundary): total bytes incl. records | 3,223 | 1,646 |

Both trees gave identical answers; every proof was verified.

## Fanout 128 (EMB-tree: f_e = 128, f_k = 2); tree height MB 2, EMB 2

| Measurement (µs per operation) | MB-tree | EMB-tree |
|---|---:|---:|
| Insert (per record) | 47.3 | 481.4 |
| Read: lookup only | 2.0 | 2.0 |
| Read: full read() incl. proof | 13.2 | 17.4 |
| Proof generation (read) | 11.2 | 14.5 |
| Verification (read) | 99.0 | 65.5 |
| Range read: lookup only | 18.7 | 18.7 |
| Range read: full read_range() incl. proof | 72.6 | 141.2 |
| Proof generation (range) | 53.9 | 122.4 |
| Verification (range) | 386.4 | 454.1 |
| Update | 58.3 | 53.7 |

| Proof size (average) | MB-tree | EMB-tree |
|---|---:|---:|
| read: hashes | 201.3 | 13.6 |
| read: hash bytes | 6,441 | 435 |
| read: total bytes incl. records | 6,464 | 458 |
| range (50 records + 2 boundary): hashes | 202.6 | 13.6 |
| range (50 records + 2 boundary): hash bytes | 6,482 | 436 |
| range (50 records + 2 boundary): total bytes incl. records | 7,673 | 1,628 |

Both trees gave identical answers; every proof was verified.

## Summary: average hashes per proof

| Fanout | Read: MB | Read: EMB | Range: MB | Range: EMB |
|---:|---:|---:|---:|---:|
| 8 | 25.0 | 14.1 | 25.1 | 14.3 |
| 32 | 64.3 | 14.2 | 63.5 | 14.2 |
| 128 | 201.3 | 13.6 | 202.6 | 13.6 |

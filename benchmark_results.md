# Benchmark: MB-tree vs EMB-tree

- 10,000 records inserted in random order (seed 42); 1,000 reads, 200 range reads of 50 records, 1,000 updates
- times: microseconds per operation, median of 5 runs (the two trees take turns); proof generation = full read - lookup only
- timings move by tens of percent between runs on a laptop, so only large differences mean something; proof sizes are exact
- Python 3.14.0 on Windows-11-10.0.26300-SP0

## Fanout 8 (EMB-tree: f_e = 8, f_k = 2, 8 slots per node); tree height MB 6, EMB 6

| Measurement (µs per operation) | MB-tree | EMB-tree |
|---|---:|---:|
| Insert (per record, incl. its non-membership proof) | 63.4 | 218.5 |
| Read: lookup only | 4.5 | 3.9 |
| Read: full read() incl. proof | 14.8 | 28.9 |
| Proof generation (read) | 9.2 | 24.8 |
| Verification (read) | 48.9 | 91.7 |
| Range read: lookup only | 26.9 | 27.2 |
| Range read: full read_range() incl. proof | 82.5 | 154.2 |
| Proof generation (range) | 63.9 | 126.6 |
| Verification (range) | 360.9 | 646.5 |
| Update | 36.4 | 97.6 |

| Proof size (average) | MB-tree | EMB-tree |
|---|---:|---:|
| read: hashes | 25.0 | 18.0 |
| read: of which empty slots (E) | 0.0 | 3.9 |
| read: hash bytes | 799 | 576 |
| read: total bytes incl. records | 825 | 602 |
| range (50 records + 2 boundary): hashes | 25.1 | 30.7 |
| range (50 records + 2 boundary): of which empty slots (E) | 0.0 | 16.5 |
| range (50 records + 2 boundary): hash bytes | 802 | 983 |
| range (50 records + 2 boundary): total bytes incl. records | 2,145 | 2,327 |

Both trees gave identical answers; every proof was verified.

## Fanout 32 (EMB-tree: f_e = 32, f_k = 2, 32 slots per node); tree height MB 3, EMB 3

| Measurement (µs per operation) | MB-tree | EMB-tree |
|---|---:|---:|
| Insert (per record, incl. its non-membership proof) | 59.3 | 491.7 |
| Read: lookup only | 2.5 | 2.7 |
| Read: full read() incl. proof | 11.1 | 29.1 |
| Proof generation (read) | 8.3 | 26.4 |
| Verification (read) | 56.4 | 104.4 |
| Range read: lookup only | 22.9 | 45.8 |
| Range read: full read_range() incl. proof | 89.6 | 100.5 |
| Proof generation (range) | 58.3 | 71.6 |
| Verification (range) | 345.9 | 726.6 |
| Update | 36.2 | 90.0 |

| Proof size (average) | MB-tree | EMB-tree |
|---|---:|---:|
| read: hashes | 64.3 | 15.0 |
| read: of which empty slots (E) | 0.0 | 0.8 |
| read: hash bytes | 2,056 | 480 |
| read: total bytes incl. records | 2,082 | 506 |
| range (50 records + 2 boundary): hashes | 63.5 | 20.4 |
| range (50 records + 2 boundary): of which empty slots (E) | 0.0 | 6.2 |
| range (50 records + 2 boundary): hash bytes | 2,031 | 651 |
| range (50 records + 2 boundary): total bytes incl. records | 3,374 | 1,995 |

Both trees gave identical answers; every proof was verified.

## Fanout 128 (EMB-tree: f_e = 128, f_k = 2, 128 slots per node); tree height MB 2, EMB 2

| Measurement (µs per operation) | MB-tree | EMB-tree |
|---|---:|---:|
| Insert (per record, incl. its non-membership proof) | 81.0 | 1052.4 |
| Read: lookup only | 3.1 | 2.1 |
| Read: full read() incl. proof | 14.9 | 17.3 |
| Proof generation (read) | 12.6 | 15.3 |
| Verification (read) | 120.3 | 78.6 |
| Range read: lookup only | 25.7 | 20.1 |
| Range read: full read_range() incl. proof | 58.7 | 112.4 |
| Proof generation (range) | 37.7 | 80.6 |
| Verification (range) | 508.9 | 624.8 |
| Update | 75.9 | 100.6 |

| Proof size (average) | MB-tree | EMB-tree |
|---|---:|---:|
| read: hashes | 201.3 | 14.0 |
| read: of which empty slots (E) | 0.0 | 0.4 |
| read: hash bytes | 6,441 | 448 |
| read: total bytes incl. records | 6,467 | 474 |
| range (50 records + 2 boundary): hashes | 202.6 | 15.7 |
| range (50 records + 2 boundary): of which empty slots (E) | 0.0 | 2.1 |
| range (50 records + 2 boundary): hash bytes | 6,482 | 504 |
| range (50 records + 2 boundary): total bytes incl. records | 7,825 | 1,847 |

Both trees gave identical answers; every proof was verified.

## Summary: average hashes per proof (EMB-tree: of which empty slots)

| Fanout | Read: MB | Read: EMB | Range: MB | Range: EMB |
|---:|---:|---:|---:|---:|
| 8 | 25.0 | 18.0 (3.9 E) | 25.1 | 30.7 (16.5 E) |
| 32 | 64.3 | 15.0 (0.8 E) | 63.5 | 20.4 (6.2 E) |
| 128 | 201.3 | 14.0 (0.4 E) | 202.6 | 15.7 (2.1 E) |

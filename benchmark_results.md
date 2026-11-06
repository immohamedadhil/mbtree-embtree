# Benchmark: MB-tree vs EMB-tree

- 10,000 records inserted in random order (seed 42); 1,000 reads, 200 range reads of 50 records, 1,000 updates
- times: microseconds per operation, median of 5 runs (the two trees take turns); proof generation = full read - lookup only
- timings move by tens of percent between runs on a laptop, so only large differences mean something; proof sizes are exact
- Python 3.15.2 on Windows-11-10.0.26220-SP0

## Fanout 8 (EMB-tree: f_e = 8, f_k = 2, 8 slots per node); tree height MB 6, EMB 6

| Measurement (µs per operation) | MB-tree | EMB-tree |
|---|---:|---:|
| Insert (per record, incl. its non-membership proof) | 31.6 | 130.6 |
| Read: lookup only | 2.3 | 2.4 |
| Read: full read() incl. proof | 8.5 | 13.8 |
| Proof generation (read) | 6.3 | 11.5 |
| Verification (read) | 21.4 | 44.2 |
| Range read: lookup only | 18.5 | 21.2 |
| Range read: full read_range() incl. proof | 66.2 | 95.0 |
| Proof generation (range) | 48.7 | 64.8 |
| Verification (range) | 195.7 | 323.1 |
| Update | 25.8 | 55.1 |

| Proof size (average) | MB-tree | EMB-tree |
|---|---:|---:|
| read: hashes | 24.8 | 18.0 |
| read: of which empty slots (E) | 0.0 | 4.0 |
| read: hash bytes | 794 | 576 |
| read: total bytes incl. records | 820 | 602 |
| range (50 records + 2 boundary): hashes | 24.2 | 33.0 |
| range (50 records + 2 boundary): of which empty slots (E) | 0.0 | 19.3 |
| range (50 records + 2 boundary): hash bytes | 773 | 1,056 |
| range (50 records + 2 boundary): total bytes incl. records | 2,116 | 2,399 |

Both trees gave identical answers; every proof was verified.

## Fanout 32 (EMB-tree: f_e = 32, f_k = 2, 32 slots per node); tree height MB 3, EMB 3

| Measurement (µs per operation) | MB-tree | EMB-tree |
|---|---:|---:|
| Insert (per record, incl. its non-membership proof) | 27.7 | 178.3 |
| Read: lookup only | 1.5 | 1.7 |
| Read: full read() incl. proof | 5.7 | 10.8 |
| Proof generation (read) | 4.2 | 9.2 |
| Verification (read) | 23.8 | 36.4 |
| Range read: lookup only | 14.7 | 14.8 |
| Range read: full read_range() incl. proof | 30.7 | 54.4 |
| Proof generation (range) | 16.6 | 40.4 |
| Verification (range) | 154.5 | 269.6 |
| Update | 16.7 | 35.3 |

| Proof size (average) | MB-tree | EMB-tree |
|---|---:|---:|
| read: hashes | 64.4 | 15.0 |
| read: of which empty slots (E) | 0.0 | 1.4 |
| read: hash bytes | 2,059 | 480 |
| read: total bytes incl. records | 2,085 | 506 |
| range (50 records + 2 boundary): hashes | 64.4 | 20.1 |
| range (50 records + 2 boundary): of which empty slots (E) | 0.0 | 6.4 |
| range (50 records + 2 boundary): hash bytes | 2,059 | 642 |
| range (50 records + 2 boundary): total bytes incl. records | 3,403 | 1,985 |

Both trees gave identical answers; every proof was verified.

## Fanout 128 (EMB-tree: f_e = 128, f_k = 2, 128 slots per node); tree height MB 2, EMB 2

| Measurement (µs per operation) | MB-tree | EMB-tree |
|---|---:|---:|
| Insert (per record, incl. its non-membership proof) | 29.2 | 394.9 |
| Read: lookup only | 1.3 | 1.3 |
| Read: full read() incl. proof | 7.7 | 8.7 |
| Proof generation (read) | 6.4 | 7.2 |
| Verification (read) | 51.5 | 37.8 |
| Range read: lookup only | 16.4 | 13.6 |
| Range read: full read_range() incl. proof | 41.3 | 42.7 |
| Proof generation (range) | 24.3 | 30.3 |
| Verification (range) | 220.6 | 290.1 |
| Update | 24.5 | 35.3 |

| Proof size (average) | MB-tree | EMB-tree |
|---|---:|---:|
| read: hashes | 202.6 | 14.0 |
| read: of which empty slots (E) | 0.0 | 0.3 |
| read: hash bytes | 6,485 | 448 |
| read: total bytes incl. records | 6,511 | 474 |
| range (50 records + 2 boundary): hashes | 198.0 | 15.5 |
| range (50 records + 2 boundary): of which empty slots (E) | 0.0 | 2.2 |
| range (50 records + 2 boundary): hash bytes | 6,337 | 496 |
| range (50 records + 2 boundary): total bytes incl. records | 7,680 | 1,839 |

Both trees gave identical answers; every proof was verified.

## Summary: average hashes per proof (EMB-tree: of which empty slots)

| Fanout | Read: MB | Read: EMB | Range: MB | Range: EMB |
|---:|---:|---:|---:|---:|
| 8 | 24.8 | 18.0 (4.0 E) | 24.2 | 33.0 (19.3 E) |
| 32 | 64.4 | 15.0 (1.4 E) | 64.4 | 20.1 (6.4 E) |
| 128 | 202.6 | 14.0 (0.3 E) | 198.0 | 15.5 (2.2 E) |

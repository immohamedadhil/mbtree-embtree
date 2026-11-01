# Results: MB-tree vs EMB-tree

## Summary

- **Correctness.** Both trees give identical answers on the same operations, every
  honest proof verifies, and every tampered answer or proof that we tried is rejected
  (101 unit tests and the toy demo).
- **Proof size.** The EMB-tree's proofs are much smaller, and the gap grows with the
  fanout: 25 vs 14 hashes per read at fanout 8, 201 vs 14 at fanout 128. With f_k = 2
  the EMB-tree needs about log₂ N hashes whatever the fanout, as the paper predicts.
- **Cost.** The EMB-tree pays with time: inserts are about 4–10× slower (mostly
  because our inserts rebuild the small trees, see Limitations), and proof generation
  is slower at every fanout. Verification is slower too, except for reads at fanout
  128, where the MB-tree's large nodes make it the slower one. Updates are slower at
  fanouts 8 and 32 and about equal at 128.

## 1. Correctness

| Tests (`python -m unittest -v test_trees`) | Count |
|---|---:|
| Plain B+-tree: toy shape, every insert order of 7 keys, 1,000 random keys vs a Python `dict`, edge cases | 13 |
| The same 13 tests on the MB-tree and on the EMB-tree, with all hashes re-checked | 26 |
| Hashing: SHA-256 test vector, unambiguous record encoding, 0x00/0x01 labels | 3 |
| Hash maintenance: toy roots worked out by hand, only the path re-hashed on update, hashes correct after every random operation, EMB with f_k ≥ f_e equal to the MB-tree | 12 |
| Reads: hand-worked proofs, all keys verify, proven "not found", tampering rejected (any flipped bit, changed value/key/shape, wrong or old root, false "not found") | 23 |
| Ranges: hand-worked proofs, edge and random ranges, completeness attacks (hiding any record or subtree), tampering rejected | 23 |
| Both trees agree on the same 1,500 random inserts, updates, reads and range reads (4 fanout settings) | 1 |
| **Total** (all pass on Python 3.12 and 3.14) | **101** |

## 2. The 16-key toy example (`python demo_toy16.py`)

Keys 1–16 inserted in order, fanout 4, EMB-tree f_k = 2. Tree:
`[10]` / `[4 7] [13]` / `[1 2 3] [4 5 6] [7 8 9] [10 11 12] [13 14 15 16]`.

| Proof (number of hashes) | MB-tree | EMB-tree |
|---|---:|---:|
| `read(2)` | 5 | 5 |
| `read(14)` | 5 | 4 |
| `read(99)` (proof that 99 is absent) | 5 | 4 |
| `read_range(1, 5)` (+ boundary record 6) | 2 | 2 |
| `read_range(9, 12)` (+ boundary records 8 and 13) | 6 | 4 |
| All 16 reads together | 77 | 66 |

Nodes this small hold only 3–4 entries, so the two trees differ little; the
benchmark uses larger fanouts to show the difference.

## 3. Benchmark (`python benchmark.py`, full output in `benchmark_results.md`)

10,000 records inserted in random order (seed 42); 1,000 reads; 200 range reads of
50 records each; 1,000 updates. The same data and operations for both trees. EMB-tree
f_k = 2. Times are microseconds per operation, the median of 5 runs. Python 3.14,
Windows 11 laptop.

**Proof size** (average; exact, does not vary between runs)

| Fanout | Read: MB | Read: EMB | Range: MB | Range: EMB | Range total bytes incl. 52 records: MB | EMB |
|---:|---:|---:|---:|---:|---:|---:|
| 8 | 25.0 hashes (799 B) | 14.1 (453 B) | 25.1 (802 B) | 14.3 (456 B) | 1,993 | 1,648 |
| 32 | 64.3 (2,056 B) | 14.2 (455 B) | 63.5 (2,031 B) | 14.2 (454 B) | 3,223 | 1,646 |
| 128 | 201.3 (6,441 B) | 13.6 (435 B) | 202.6 (6,482 B) | 13.6 (436 B) | 7,673 | 1,628 |

**Time** (µs per operation, MB-tree / EMB-tree)

| Operation | Fanout 8 | Fanout 32 | Fanout 128 |
|---|---:|---:|---:|
| Insert | 33.8 / 126.3 | 32.6 / 206.3 | 47.3 / 481.4 |
| Read: lookup only | 3.2 / 3.6 | 2.2 / 2.3 | 2.0 / 2.0 |
| Proof generation (read) | 9.5 / 18.7 | 7.3 / 15.9 | 11.2 / 14.5 |
| Verification (read) | 38.7 / 73.8 | 47.8 / 69.3 | 99.0 / 65.5 |
| Range read: lookup only | 24.1 / 23.8 | 19.4 / 20.1 | 18.7 / 18.7 |
| Proof generation (range) | 53.6 / 213.7 | 39.9 / 135.9 | 53.9 / 122.4 |
| Verification (range) | 304.3 / 469.0 | 296.2 / 456.0 | 386.4 / 454.1 |
| Update | 37.4 / 64.6 | 32.3 / 56.9 | 58.3 / 53.7 |

## 4. Comparison with the paper

- **Proof size matches the paper.** "The EMB-tree and its variants, logically work as
  an MB-tree with fanout f_k and hence their VO sizes are significantly reduced"
  (Section 6.2.2). The MB-tree's proofs grow with the fanout (about (f − 1) hashes per
  level), while the EMB-tree with f_k = 2 stays near log₂ 10,000 ≈ 13.3 hashes: it acts
  like one binary Merkle tree over all records. The paper: "For f_k = 2 the
  authentication cost becomes equal to a Merkle hash tree, which has the minimal VO
  size but higher verification time" (Section 3.3).
- **Verification time mostly matches ("higher verification time").** For reads at
  fanouts 8 and 32 the EMB-tree verifies more slowly: it hashes in many small steps,
  and in Python each step has a fixed cost. At fanout 128 the MB-tree is slower for
  reads, because each of its steps hashes about 4 KB and its proofs hold about 200
  hashes. For ranges the EMB-tree is slower at all three fanouts: both trees re-hash
  the 52 records, and the EMB-tree also hashes the small groups above them.
- **Inserts.** The paper also finds that "the EMB-tree approaches increase the number
  of hashes that need to be computed", but that the extra time is small next to the
  total construction cost, where disk I/O dominates (Section 6.2.1). In memory there
  is no I/O to hide it, and our inserts rebuild the changed small trees, so the gap
  here (about 4–10×) is larger than the paper's.
- **Updates** re-hash only the path in both trees (Sections 4.2–4.3, checked by tests
  that count hash calls). The EMB-tree makes more but smaller hash calls; it is slower
  at fanouts 8 and 32 and about equal at 128.
- **Lookups** run the same B+-tree code in both trees; their differences are noise.

## 5. Limitations

- **Timing noise.** On this laptop the same measurement varied by up to about 50%
  between runs. The two trees take turns run by run so that both see the same machine
  state, but only large differences should be trusted. Proof sizes are exact.
- **Absolute times are not comparable with the paper's**: Python instead of the
  paper's prototype, SHA-256 instead of SHA-1, and no disk, so the I/O costs that
  dominate the paper's results are absent.
- **EMB-tree inserts rebuild the changed small trees** (README, assumption 2), which
  inflates the EMB-tree's insert time compared with the paper's cost model.
- **Same fanout for both trees.** In the paper the EMB-tree's fanout is smaller
  because its small trees use page space; here both fanouts are set directly.
- **Proof generation time** is a difference of two measurements (full read minus
  lookup), so it carries the noise of both.
- **Proof size** counts hashes and records, not the nesting information, because no
  wire format was defined (the paper's estimate for it is one byte per node).
- **Scope.** A small dataset (10,000 records) as the task asks; no delete, no
  signatures, integer keys and text values only.

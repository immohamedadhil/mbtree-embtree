# Results: MB-tree vs EMB-tree

## Summary

- **Correctness.** Both trees give identical answers on the same operations, every
  honest proof verifies, and every tampered answer or proof that we tried is rejected
  (91 unit tests and the toy demo). Every insert comes with a proof that its key was
  new, and every kind of missing key is proven (README, "Missing keys: every case").
- **Proof size.** The EMB-tree's read proofs are much smaller, and the gap grows with
  the fanout: 25.0 vs 18.0 hashes at fanout 8, 201.3 vs 14.0 at fanout 128. Because the
  empty slots make every node full, an EMB read proof has exactly (f_k − 1)·d_k hashes
  per node, the paper's count. Range proofs are much smaller at fanouts 32 and 128,
  but **larger at fanout 8** (30.7 vs 25.1 hashes), where more than half of the
  EMB-tree's hashes are empty slots.
- **Cost.** The EMB-tree pays with time: inserts are about 3–13× slower (they rebuild
  the small trees, see Limitations), proof generation and updates are slower at every
  fanout, and verification is slower too, except for reads at fanout 128, where the
  MB-tree's large nodes make it the slower one.

## 1. Correctness

| Tests (`python -m unittest -v test_trees`) | Count |
|---|---:|
| B+-tree rules on the MB-tree, with all hashes re-checked: toy shape, every insert order of 7 keys, 1,000 random keys vs a Python `dict`, edge cases, errors | 13 |
| The same 13 tests on the EMB-tree | 13 |
| Hashing: SHA-256 test vector, record encoding (exact bytes, unambiguous), 0x00/0x01 labels | 3 |
| Hash maintenance: toy roots worked out by hand, the padding rule, only the path re-hashed on update, hashes correct after every random operation, EMB with f_k ≥ f_e equal to the MB-tree | 12 |
| Reads: hand-worked proofs, all keys verify, tampering rejected (any flipped bit, changed value/key/shape, wrong or old root, false "not found") | 21 |
| Ranges: hand-worked proofs, edge and random ranges, completeness attacks (hiding any record or subtree), tampering rejected | 19 |
| Missing keys and inserts: every case of a missing key on both trees, signpost keys, false "not found" rejected, every insert's non-membership proof | 6 |
| Empty slots: a server can neither hide a record behind EMPTY nor add or remove EMPTY slots; MB-tree proofs accept none | 3 |
| Both trees agree on the same 1,500 random inserts, updates, reads and range reads (4 fanout settings) | 1 |
| **Total** (all pass on Python 3.12 and 3.14) | **91** |

We also checked the tests themselves: 21 deliberately broken versions of the code (one
small bug each, in the trees, the verifier and the record encoding) were each caught by
at least one test.

## 2. The 16-key toy example (`python demo_toy16.py`)

Keys 1–16 inserted in order, fanout 4, EMB-tree f_k = 2 (4 slots per node). Tree:
`[10]` / `[4 7] [13]` / `[1 2 3] [4 5 6] [7 8 9] [10 11 12] [13 14 15 16]`.

The demo shows `read(14)` and `read_range(5, 9)` (the first two rows); the other rows
are measured on the same tree.

| Proof (number of hashes; E = empty slots among them) | MB-tree | EMB-tree |
|---|---:|---:|
| `read(14)` (in the demo) | 5 | 6 (2 E) |
| `read_range(5, 9)` (+ boundary records 4 and 10; in the demo) | 4 | 9 (5 E) |
| `read(2)` | 5 | 6 (1 E) |
| `read(99)` (proof that 99 is absent) | 5 | 6 (2 E) |
| `read_range(1, 5)` (+ boundary record 6) | 2 | 5 (3 E) |
| `read_range(9, 12)` (+ boundary records 8 and 13) | 6 | 9 (5 E) |
| All 16 reads together | 77 | 96 (30 E) |

Nodes this small hold only 2–4 entries in 4 slots, so the EMB-tree's proofs carry
empty slots and come out a little larger; without them they would be smaller (66 vs
77 hashes for all 16 reads). The benchmark uses larger fanouts to show the difference.

## 3. Benchmark (`python benchmark.py`, full output in `benchmark_results.md`)

10,000 records inserted in random order (seed 42); 1,000 reads; 200 range reads of
50 records each; 1,000 updates. The same data and operations for both trees. EMB-tree
f_k = 2, so 8, 32 and 128 slots per node. Times are microseconds per operation, the
median of 5 runs. Python 3.14, Windows 11 laptop.

**Proof size** (average; exact, does not vary between runs)

| Fanout | Read: MB | Read: EMB (of which E) | Range: MB | Range: EMB (of which E) | Range total bytes incl. 52 records: MB | EMB |
|---:|---:|---:|---:|---:|---:|---:|
| 8 | 25.0 hashes (799 B) | 18.0 (3.9) (576 B) | 25.1 (802 B) | 30.7 (16.5) (983 B) | 2,145 | 2,327 |
| 32 | 64.3 (2,056 B) | 15.0 (0.8) (480 B) | 63.5 (2,031 B) | 20.4 (6.2) (651 B) | 3,374 | 1,995 |
| 128 | 201.3 (6,441 B) | 14.0 (0.4) (448 B) | 202.6 (6,482 B) | 15.7 (2.1) (504 B) | 7,825 | 1,847 |

**Time** (µs per operation, MB-tree / EMB-tree)

| Operation | Fanout 8 | Fanout 32 | Fanout 128 |
|---|---:|---:|---:|
| Insert (incl. its non-membership proof) | 63.4 / 218.5 | 59.3 / 491.7 | 81.0 / 1052.4 |
| Read: lookup only | 4.5 / 3.9 | 2.5 / 2.7 | 3.1 / 2.1 |
| Proof generation (read) | 9.2 / 24.8 | 8.3 / 26.4 | 12.6 / 15.3 |
| Verification (read) | 48.9 / 91.7 | 56.4 / 104.4 | 120.3 / 78.6 |
| Range read: lookup only | 26.9 / 27.2 | 22.9 / 45.8 | 25.7 / 20.1 |
| Proof generation (range) | 63.9 / 126.6 | 58.3 / 71.6 | 37.7 / 80.6 |
| Verification (range) | 360.9 / 646.5 | 345.9 / 726.6 | 508.9 / 624.8 |
| Update | 36.4 / 97.6 | 36.2 / 90.0 | 75.9 / 100.6 |

## 4. Comparison with the paper

- **Proof size matches the paper.** The paper assumes "that f_e is a power of f_k such
  that the embedded trees when bulk-loaded are always full", and then "the total number
  of values inserted in the VO per node is reduced to (f_k − 1)d_k" (Section 3.3). The
  empty slots make our nodes full in the same way, so with f_k = 2 a read proof has
  exactly d_k hashes per node: 3 × 6 levels = 18 at fanout 8, 5 × 3 = 15 at fanout 32,
  7 × 2 = 14 at fanout 128, which is what we measured. The MB-tree's proofs grow with
  the fanout (about f − 1 hashes per level). The paper: "For f_k = 2 the authentication
  cost becomes equal to a Merkle hash tree, which has the minimal VO size but higher
  verification time" (Section 3.3). Without the empty slots our EMB read proofs would
  hold 14.1, 14.2 and 13.6 hashes, close to log₂ 10,000 ≈ 13.3.
- **Range proofs at small fanouts.** Every leaf inside a range is sent in full, with
  its empty slots. At fanout 8 a 52-record range covers about 10 leaves holding 5.7
  records in 8 slots on average: about 11 of the 16.5 empty slots come from these
  leaves, the rest from the inner nodes on the way. This makes the EMB-tree's range
  proof larger than the MB-tree's at fanout 8; at 32 and 128 the EMB-tree's is 3× and
  13× smaller.
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
  here (about 3–13×) is larger than the paper's.
- **Updates** re-hash only the path in both trees (Sections 4.2–4.3, checked by tests
  that count hash calls). The EMB-tree makes more but smaller hash calls; it is slower
  at fanouts 8 and 32, and the gap is smaller at 128.
- **Lookups** run the same B+-tree code in both trees; their differences are noise.

## 5. Limitations

- **Timing noise.** On this laptop the same measurement can differ by up to about 2×
  between runs: the range lookup at fanout 32 runs the same code in both trees, yet
  took 22.9 vs 45.8 µs. The two trees take turns run by run so that both see the same
  machine state, but only large differences should be trusted. Proof sizes are exact.
- **Absolute times are not comparable with the paper's**: Python instead of the
  paper's prototype, SHA-256 instead of SHA-1, and no disk, so the I/O costs that
  dominate the paper's results are absent.
- **EMB-tree inserts rebuild the changed small trees** (README, assumption 2), which
  inflates the EMB-tree's insert time compared with the paper's cost model. Inserts in
  both trees also include building the non-membership proof.
- **Empty slots are counted as full 32-byte hashes.** The client knows what EMPTY is,
  so a real wire format could send each one as a short marker; we count them in full,
  and also report them separately.
- **Same fanout for both trees.** In the paper the EMB-tree's fanout is smaller
  because its small trees use page space; here both fanouts are set directly.
- **Proof generation time** is a difference of two measurements (full read minus
  lookup), so it carries the noise of both.
- **Proof size** counts hashes and records, not the nesting information, because no
  wire format was defined (the paper's estimate for it is one byte per node).
- **Scope.** A small dataset (10,000 records) as the task asks; no delete, no
  signatures, integer keys and text values only.

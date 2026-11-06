# Results: MB-tree vs EMB-tree

## Summary

- **Correctness.** Both trees give identical answers on the same operations, every
  honest proof verifies, and every tampered answer or proof that I tried is rejected
  (93 unit tests and the toy demo). Every insert comes with a proof that its key was
  new, and every kind of missing key is proven (README, "Missing key").
- **Proof size.** The EMB-tree's read proofs are much smaller, and the gap grows with
  the fanout: 24.8 vs 18.0 hashes at fanout 8, 202.6 vs 14.0 at fanout 128. Because the
  empty slots make every node full, an EMB read proof has exactly (f_k − 1)·d_k hashes
  per node, the paper's count. Range proofs are much smaller at fanouts 32 and 128,
  but **larger at fanout 8** (33.0 vs 24.2 hashes), where more than half of the
  EMB-tree's hashes are empty slots.
- **Cost.** The EMB-tree pays with time: inserts are about 4–14× slower (they rebuild
  the small trees, see Limitations), proof generation and updates are slower at every
  fanout, and verification is slower too, except for reads at fanout 128, where the
  MB-tree's large nodes make it the slower one.

## 1. Correctness

| Tests (`python -m unittest -v test_trees`) | Count |
|---|---:|
| B+-tree rules on the MB-tree, with all hashes re-checked: toy shape, every insert order of 7 keys, 1,000 random keys vs a Python `dict`, edge cases, errors, the textbook's split sizes | 14 |
| The same 14 tests on the EMB-tree | 14 |
| Hashing: SHA-256 test vector, record encoding (exact bytes, unambiguous), 0x00/0x01 labels | 3 |
| Hash maintenance: toy roots worked out by hand, the padding rule, only the path re-hashed on update, hashes correct after every random operation, EMB with f_k ≥ f_e equal to the MB-tree | 12 |
| Reads: hand-worked proofs, all keys verify, tampering rejected (any flipped bit, changed value/key/shape, wrong or old root, false "not found") | 21 |
| Ranges: hand-worked proofs, edge and random ranges, completeness attacks (hiding any record or subtree), tampering rejected | 19 |
| Missing keys and inserts: every case of a missing key on both trees, signpost keys, false "not found" rejected, every insert's non-membership proof | 6 |
| Empty slots: a server can neither hide a record behind EMPTY nor add or remove EMPTY slots; MB-tree proofs accept none | 3 |
| Both trees agree on the same 1,500 random inserts, updates, reads and range reads (4 fanout settings) | 1 |
| **Total** (all pass on Python 3.15) | **93** |

The B+-tree checks use the node sizes of Silberschatz, Korth and Sudarshan, *Database
System Concepts* (7th ed., Section 14.3): with n = fanout, an inner node has ⌈n/2⌉ to n
children and a leaf ⌈(n−1)/2⌉ to n − 1 records. With the earlier leaf size (n records)
put back, 54 of the 93 tests fail.

When the tests were first written, I also checked the tests themselves: 21 deliberately
broken versions of the code (one small bug each, in the trees, the verifier and the
record encoding) were each caught by at least one test.

## 2. The 16-key toy example (`python demo_toy16.py`)

Keys 1–16 inserted in order, fanout 4 (a leaf holds at most 3 keys), EMB-tree f_k = 2
(4 slots per node). Tree:
`[7 13]` / `[3 5] [9 11] [15]` / `[1 2] [3 4] [5 6] [7 8] [9 10] [11 12] [13 14] [15 16]`.

The demo shows `read(14)` and `read_range(5, 9)` (the first two rows); the other rows
are measured on the same tree.

| Proof (number of hashes; E = empty slots among them) | MB-tree | EMB-tree |
|---|---:|---:|
| `read(14)` (in the demo) | 4 | 6 (3 E) |
| `read_range(5, 9)` (+ boundary records 4 and 10; in the demo) | 4 | 9 (5 E) |
| `read(2)` | 5 | 6 (1 E) |
| `read(99)` (proof that 99 is absent) | 4 | 6 (3 E) |
| `read_range(1, 5)` (+ boundary record 6) | 2 | 6 (4 E) |
| `read_range(9, 12)` (+ boundary records 8 and 13) | 4 | 11 (7 E) |
| All 16 reads together | 76 | 96 (28 E) |

Nodes this small hold only 2–3 entries in 4 slots, so the EMB-tree's proofs carry
empty slots and come out larger; without them they would be smaller (68 vs 76 hashes
for all 16 reads). The benchmark uses larger fanouts to show the difference.

## 3. Benchmark (`python benchmark.py`, full output in `benchmark_results.md`)

10,000 records inserted in random order (seed 42); 1,000 reads; 200 range reads of
50 records each; 1,000 updates. The same data and operations for both trees. EMB-tree
f_k = 2, so 8, 32 and 128 slots per node. Times are microseconds per operation, the
median of 5 runs. Python 3.15, Windows 11 laptop.

**Proof size** (average; exact, does not vary between runs)

| Fanout | Read: MB | Read: EMB (of which E) | Range: MB | Range: EMB (of which E) | Range total bytes incl. 52 records: MB | EMB |
|---:|---:|---:|---:|---:|---:|---:|
| 8 | 24.8 hashes (794 B) | 18.0 (4.0) (576 B) | 24.2 (773 B) | 33.0 (19.3) (1,056 B) | 2,116 | 2,399 |
| 32 | 64.4 (2,059 B) | 15.0 (1.4) (480 B) | 64.4 (2,059 B) | 20.1 (6.4) (642 B) | 3,403 | 1,985 |
| 128 | 202.6 (6,485 B) | 14.0 (0.3) (448 B) | 198.0 (6,337 B) | 15.5 (2.2) (496 B) | 7,680 | 1,839 |

**Time** (µs per operation, MB-tree / EMB-tree)

| Operation | Fanout 8 | Fanout 32 | Fanout 128 |
|---|---:|---:|---:|
| Insert (incl. its non-membership proof) | 31.6 / 130.6 | 27.7 / 178.3 | 29.2 / 394.9 |
| Read: lookup only | 2.3 / 2.4 | 1.5 / 1.7 | 1.3 / 1.3 |
| Proof generation (read) | 6.3 / 11.5 | 4.2 / 9.2 | 6.4 / 7.2 |
| Verification (read) | 21.4 / 44.2 | 23.8 / 36.4 | 51.5 / 37.8 |
| Range read: lookup only | 18.5 / 21.2 | 14.7 / 14.8 | 16.4 / 13.6 |
| Proof generation (range) | 48.7 / 64.8 | 16.6 / 40.4 | 24.3 / 30.3 |
| Verification (range) | 195.7 / 323.1 | 154.5 / 269.6 | 220.6 / 290.1 |
| Update | 25.8 / 55.1 | 16.7 / 35.3 | 24.5 / 35.3 |

## 4. Comparison with the paper

- **Proof size matches the paper.** The paper assumes "that f_e is a power of f_k such
  that the embedded trees when bulk-loaded are always full", and then "the total number
  of values inserted in the VO per node is reduced to (f_k − 1)d_k" (Section 3.3). The
  empty slots make my nodes full in the same way, so with f_k = 2 a read proof has
  exactly d_k hashes per node: 3 × 6 levels = 18 at fanout 8, 5 × 3 = 15 at fanout 32,
  7 × 2 = 14 at fanout 128, which is what I measured. The MB-tree's proofs grow with
  the fanout (about f − 1 hashes per level). The paper: "For f_k = 2 the authentication
  cost becomes equal to a Merkle hash tree, which has the minimal VO size but higher
  verification time" (Section 3.3). Without the empty slots my EMB read proofs would
  hold 14.0, 13.6 and 13.7 hashes, close to log₂ 10,000 ≈ 13.3.
- **Range proofs at small fanouts.** Every leaf inside a range is sent in full, with
  its empty slots. At fanout 8 a leaf holds at most 7 records in 8 slots, and about 5
  on average, so a 52-record range covers about 10 leaves, and most of the 19.3 empty
  slots come from these leaves. This makes the EMB-tree's range proof larger than the
  MB-tree's at fanout 8; at 32 and 128 the EMB-tree's is 3× and 13× smaller.
- **Verification time mostly matches ("higher verification time").** For reads at
  fanouts 8 and 32 the EMB-tree verifies more slowly: it hashes in many small steps,
  and in Python each step has a fixed cost. At fanout 128 the MB-tree is slower for
  reads, because each of its steps hashes about 4 KB and its proofs hold about 200
  hashes. For ranges the EMB-tree is slower at all three fanouts: both trees re-hash
  the 52 records, and the EMB-tree also hashes the small groups above them.
- **Inserts.** The paper also finds that "the EMB-tree approaches increase the number
  of hashes that need to be computed", but that the extra time is small next to the
  total construction cost, where disk I/O dominates (Section 6.2.1). In memory there
  is no I/O to hide it, and my inserts rebuild the changed small trees, so the gap
  here (about 4–14×) is larger than the paper's.
- **Updates** re-hash only the path in both trees (Sections 4.2–4.3, checked by tests
  that count hash calls). The EMB-tree makes more but smaller hash calls; it is slower
  at fanouts 8 and 32, and the gap is smaller at 128.
- **Lookups** run the same B+-tree code in both trees; their differences are noise.

## 5. Limitations

- **Timing noise.** On a laptop the same measurement can differ by tens of percent, up
  to about 2×, between runs: the range lookup at fanout 128 runs the same code in both
  trees, yet took 16.4 vs 13.6 µs. The two trees take turns run by run so that both see
  the same machine state, but only large differences should be trusted. Proof sizes are
  exact.
- **Absolute times are not comparable with the paper's**: Python instead of the
  paper's prototype, SHA-256 instead of SHA-1, and no disk, so the I/O costs that
  dominate the paper's results are absent.
- **EMB-tree inserts rebuild the changed small trees** (README, assumption 2), which
  inflates the EMB-tree's insert time compared with the paper's cost model. Inserts in
  both trees also include building the non-membership proof.
- **Empty slots are counted as full 32-byte hashes.** The client knows what EMPTY is,
  so a real wire format could send each one as a short marker; I count them in full,
  and also report them separately.
- **Same fanout for both trees.** In the paper the EMB-tree's fanout is smaller
  because its small trees use page space; here both fanouts are set directly.
- **Proof generation time** is a difference of two measurements (full read minus
  lookup), so it carries the noise of both.
- **Proof size** counts hashes and records, not the nesting information, because no
  wire format was defined (the paper's estimate for it is one byte per node).
- **Scope.** A small dataset (10,000 records) as the task asks; no delete, no
  signatures, integer keys and text values only.

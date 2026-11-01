# MB-tree and EMB-tree: authenticated B+-trees in Python

Author: Mohamed Adhil J

An in-memory Python 3 implementation of the **Merkle B-tree (MB-tree)** and the
**Embedded Merkle B-tree (EMB-tree)** from F. Li, M. Hadjieleftheriou, G. Kollios
and L. Reyzin, *Dynamic Authenticated Index Structures for Outsourced Databases*,
SIGMOD 2006 (Sections 3.2, 3.3, 4.2–4.3).

Both trees support `insert`, `read` (with a proof), `read_range` (with a proof of
correctness and completeness) and `update`. A separate client-side module checks
every proof against an independently supplied trusted root hash.
The comparison of the two trees is in [RESULTS.md](RESULTS.md).

## Files

| File | Contents |
|---|---|
| `bptree.py` | Plain B+-tree shared by both trees: search, range search, insert with node splits, update |
| `hashing.py` | SHA-256 record and node hashes; record encoding |
| `mbtree.py` | MB-tree (Section 3.2; updates Section 4.2) |
| `embtree.py` | EMB-tree (Section 3.3; updates Section 4.3) |
| `verify.py` | Client side: `verify_read`, `verify_range`. Uses only the answer, the proof and the trusted root, never the tree |
| `test_trees.py` | 101 unit tests |
| `demo_toy16.py` | The 16-key toy example on both trees |
| `benchmark.py` | Benchmark; its latest output is `benchmark_results.md` |

## Setup

Python 3 with the standard library only; nothing to install.
Tested with Python 3.12 and 3.14 on Windows 11.

```
git clone <repository-url>
cd <repository-folder>
```

## Commands

```
python -m unittest -v test_trees    # all tests (about 35 s)
python demo_toy16.py                # 16-key toy example; exit code 0 = every check passed
python benchmark.py                 # benchmark with the default parameters (about 1 min)
python benchmark.py --keys 2000 --fanouts 8 32 --fk 2 --repeats 3 --seed 42   # other parameters
```

## Using the trees

```python
from embtree import EMBTree
from mbtree import MBTree
from verify import verify_range, verify_read

tree = EMBTree(fanout=4, fk=2)            # or MBTree(fanout=4)
for key, value in [(1, "ball"), (2, "car"), (3, "doll"), (5, "yo-yo")]:
    tree.insert(key, value)
root = tree.root_hash                     # published by the owner; trusted by the client

value, proof = tree.read(2)               # server side
assert verify_read(2, value, proof, root)                  # client side

value, proof = tree.read(4)               # missing key: value is None, proof shows absence
assert value is None and verify_read(4, None, proof, root)

records, proof = tree.read_range(2, 4)    # records [(2, "car"), (3, "doll")]
assert verify_range(2, 4, records, proof, root)

tree.update(2, "bike")                    # the root hash changes; old answers no longer verify
```

## How it works

- **Hashes (Section 3.2).** A leaf entry carries h = H(0x00 ‖ record). A node's
  hash is H(0x01 ‖ h₁ ‖ … ‖ hₙ) over its entries. In the EMB-tree a node's hash is
  instead the root of a small Merkle tree with fanout f_k over its entries (Section 3.3).
- **Read proof.** For each node on the path, bottom-up, the hashes to the left and
  to the right of the path entry: `[(left_hashes, right_hashes), ...]`. In the
  EMB-tree there is one such step per level of each node's small tree, each with at
  most f_k − 1 hashes.
- **Range proof (Section 3.2, Figure 4).** A copy of the tree in which everything the
  client does not need is replaced by its hash. It shows the answer plus one boundary
  record on each side (the largest key < low and the smallest key > high). Each node
  is a list whose items are a hash (`bytes`), a record (`(key, value)`) or a shown
  child (`list`); the nesting is the paper's node boundary information (footnote 1).
  In the EMB-tree the groups of each small tree are nested in the same way, so one
  verifier handles both trees.
- **Range check (`verify_range`).** (1) The root recomputed from the proof equals the
  trusted root; (2) no hash lies between two shown records; (3) the first shown record
  is < low, or nothing comes before it in the tree; (4) the same for the last record
  and high; (5) the answer is exactly the shown records inside [low, high].
- **Updates (Sections 4.2–4.3).** `update` re-hashes the record and only the path to
  the root; in the EMB-tree, only one path through each small tree on the way.

## Parameters

| Parameter | Meaning | Values used |
|---|---|---|
| `fanout` | Maximum entries per node (records in a leaf, children in an inner node). MB-tree fanout = EMB-tree external fanout f_e. At least 3 | Toy example: 4. Benchmark: 8, 32, 128 |
| `fk` | EMB-tree embedded fanout f_k. At least 2 | 2 (the paper's default, Section 6.2) |
| Benchmark | 10,000 records inserted in random order, seed 42; 1,000 reads and 1,000 updates; 200 range reads of 50 records; 5 runs, median | `python benchmark.py --help` |

## Assumptions and deviations from the paper

1. **Shape of the EMB-tree's small trees.** The paper assumes full nodes. For any
   node we group the entry hashes f_k at a time from the left, hash every group (even
   a group of one) and repeat until one hash is left. The small tree holds hashes
   only; the search inside a node uses the node's sorted keys. With f_k ≥ f_e this
   gives exactly the MB-tree's hashes and proofs (tested), as the paper states.
2. **EMB-tree inserts rebuild** the small trees of the nodes they change, because a
   new entry shifts the later entries into other groups. `update` recomputes only the
   paths (Section 4.3). EMB-tree inserts therefore cost more hashing than the paper's
   cost model.
3. **Hash labels.** Every hash input starts with 0x00 (record) or 0x01 (node), as in
   RFC 6962 Section 2.1, so a node hash cannot be passed off as a record hash. Records
   are encoded unambiguously: 4-byte length + signed big-endian key, then 4-byte
   length + UTF-8 value.
4. **SHA-256** instead of the paper's SHA-1, and **no signature** on the root: the
   client receives the trusted root directly (both as in the task README).
5. **In memory.** The fanout is set directly instead of being derived from a disk page
   size, and both trees use the same external fanout, so the only difference between
   them is the small tree. (In the paper the EMB-tree's fanout is smaller because the
   small trees take page space.)
6. **Where hashes are stored.** The paper keeps each child's hash in the parent's entry
   (k|p|h). Here each node keeps its own hash and the parent reads it through the
   pointer: the same value, stored once.
7. **Keys and values.** Keys are unique integers (any size, also negative); values are
   text. Inserting an existing key or updating a missing key raises `KeyError`.
8. **Splits.** An over-full node splits into two halves; with an odd count the left
   half gets the extra entry (fanout 4: 5 → 3 + 2). A leaf split copies the first key
   of the right half up; an inner split moves the middle key up.
9. **Missing keys.** `read(key)` returns `(None, proof)`, where the proof is the range
   proof for [key, key], so "not found" is proven too.
10. **Not implemented** (not required by the task): delete, batch updates (Section 4.2),
    bulk loading, signatures, the ASB-tree and the EMB⁻/EMB* variants.
11. **Benchmark definitions.** Read time = lookup only. Proof generation time = full
    `read()` / `read_range()` minus the lookup. Proof size = number of hashes (and
    bytes, 32 each); "total bytes" adds the records sent (answer and boundary records).
    The nesting information is not counted (the paper also leaves it out, Section 3.2).

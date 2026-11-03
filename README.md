# MB-tree and EMB-tree: authenticated B+-trees in Python

Author: Mohamed Adhil J

An in-memory Python 3 implementation of the **Merkle B-tree (MB-tree)** and the
**Embedded Merkle B-tree (EMB-tree)** from F. Li, M. Hadjieleftheriou, G. Kollios
and L. Reyzin, *Dynamic Authenticated Index Structures for Outsourced Databases*,
SIGMOD 2006 (Sections 3.2, 3.3, 4.2–4.3).

Both trees support `insert` (with a proof that the key is new), `read` (with a
proof), `read_range` (with a proof of correctness and completeness) and `update`.
A separate client-side module checks every proof against an independently
supplied trusted root hash. The comparison of the two trees is in [RESULTS.md](RESULTS.md).

## Files

| File | Contents |
|---|---|
| `mbtree.py` | MB-tree (Section 3.2; updates Section 4.2): a B+-tree whose nodes carry hashes. Search, range search, insert with node splits, update, and the proofs |
| `embtree.py` | EMB-tree (Section 3.3; updates Section 4.3): the MB-tree with a small Merkle tree inside every node. It replaces four MB-tree methods, all about one node: how it is hashed, how it is updated, and how it appears in a read proof and in a range proof |
| `hashing.py` | SHA-256 record and node hashes; record encoding |
| `verify.py` | Client side: `verify_read`, `verify_range`. Uses only the answer, the proof and the trusted root, never the tree |
| `test_trees.py` | 91 unit tests |
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
python -m unittest -v test_trees    # all tests (about 40 s)
python demo_toy16.py                # 16-key toy example; exit code 0 = every check passed
python benchmark.py                 # benchmark (about 2 min); the settings are at the top of benchmark.py
```

## Using the trees

```python
from embtree import EMBTree
from mbtree import MBTree
from verify import verify_range, verify_read

tree = EMBTree(fanout=4, fk=2)            # or MBTree(fanout=4)
for key, value in [(1, "ball"), (2, "car"), (3, "doll"), (5, "yo-yo")]:
    old_root = tree.root_hash
    proof = tree.insert(key, value)       # first proves that the key is not in the tree yet
    assert verify_read(key, None, proof, old_root)
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
  instead the root of a small Merkle tree with fanout f_k over its entries (Section 3.3),
  padded with empty slots (assumption 1).
- **Read proof.** For each node on the path, bottom-up, the hashes to the left and
  to the right of the path entry: `[(left_hashes, right_hashes), ...]`. In the
  EMB-tree there is one such step per level of each node's small tree, each with
  exactly f_k − 1 hashes.
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
- **Missing keys.** `read(key)` of a missing key returns `(None, proof)`, where the
  proof is the range proof for [key, key]: it shows the key's neighbours side by side,
  so the client sees there is nothing between them.
- **Insert.** `insert(key, value)` first builds that proof for the new key, then
  inserts, and returns the proof; it verifies against the root from *before* the insert.
- **Updates (Sections 4.2–4.3).** `update` re-hashes the record and only the path to
  the root; in the EMB-tree, only one path through each small tree on the way.

### Missing keys: every case

Where a missing key's neighbours sit decides how much of the tree its proof opens.
Every case is tested on both trees (`TestNonMembership`, keys 10, 20, …, 160, fanout 4,
f_k = 2: root [100]; inner nodes [40 | 70] and [130]; leaves [10 20 30] [40 50 60]
[70 80 90] [100 110 120] [130 140 150 160]):

| Where the key falls | Example | Records shown |
|---|---|---|
| before every key | `read(5)` | 10 |
| after every key | `read(999)` | 160 |
| inside one leaf, inside one small-tree group | `read(15)` | 10, 20 |
| inside one leaf, between two small-tree groups (matters for the EMB-tree) | `read(25)` | 20, 30 |
| between two leaves with the same parent | `read(35)` | 30, 40 |
| between two leaves with different parents | `read(95)` | 90, 100 |
| the tree is empty | `read(5)` | none |

A key equal to a signpost in an inner node is never missing: without delete, every
signpost is a copy of a real key.

## Parameters

| Parameter | Meaning | Values used |
|---|---|---|
| `fanout` | Maximum entries per node (records in a leaf, children in an inner node). MB-tree fanout = EMB-tree external fanout f_e. At least 3 | Toy example: 4. Benchmark: 8, 32, 128 |
| `fk` | EMB-tree embedded fanout f_k. At least 2 | 2 (the paper's default, Section 6.2) |
| Benchmark | 10,000 records inserted in random order, seed 42; 1,000 reads and 1,000 updates; 200 range reads of 50 records; 5 runs, median | Settings at the top of `benchmark.py` |

## Assumptions and deviations from the paper

1. **Non-full nodes in the EMB-tree** (as suggested by the task reviewer). The paper
   assumes full nodes. Here every node's small tree has a fixed number of slots: the
   smallest power of f_k that holds f_e entries (4 in the toy example; 8, 32 and 128
   in the benchmark). Unused slots hold EMPTY = 32 zero bytes, so every group is full
   and a read proof has exactly f_k − 1 hashes per small-tree level, as in the paper's
   cost model. A group of only empty slots is itself EMPTY (it is not hashed). The
   client treats EMPTY as an empty slot, not as a hidden record; a server cannot use it
   to hide a record, because the record's real hash is not EMPTY and the root would
   change (tested). With f_k ≥ f_e there is no small tree: the node is hashed exactly
   like an MB-tree node, so the two trees give the same hashes and proofs (tested), as
   the paper states. The small tree holds hashes only; the search inside a node uses
   the node's sorted keys.
2. **EMB-tree inserts rebuild** the small trees of the nodes they change, because a
   new entry shifts the later entries into other groups. `update` recomputes only the
   paths (Section 4.3). EMB-tree inserts therefore cost more hashing than the paper's
   cost model.
3. **Hash labels.** Every hash input starts with 0x00 (record) or 0x01 (node), as in
   RFC 6962 Section 2.1, so a node hash cannot be passed off as a record hash. Records
   are encoded unambiguously: 4-byte length + the key as decimal text, then 4-byte
   length + the UTF-8 value.
4. **SHA-256** instead of the paper's SHA-1, and **no signature** on the root: the
   client receives the trusted root directly (both as in the task README).
5. **In memory.** The fanout is set directly instead of being derived from a disk page
   size, and both trees use the same external fanout, so the only difference between
   them is the small tree. (In the paper the EMB-tree's fanout is smaller because the
   small trees take page space.)
6. **Where hashes are stored.** The paper keeps each child's hash in the parent's entry
   (k|p|h). Here each node keeps its own hash and the parent reads it through the
   pointer: the same value, stored once.
7. **Keys and values.** Keys are unique integers (also negative, up to the 4,300 digits
   Python can write as text); values are text. Updating a missing key raises `KeyError`.
8. **Splits.** An over-full node splits into two halves; with an odd count the left
   half gets the extra entry (fanout 4: 5 → 3 + 2). A leaf split copies the first key
   of the right half up; an inner split moves the middle key up.
9. **Non-membership proofs** (as suggested by the task reviewer). A missing key's
   `read` is proven, and every `insert` returns the proof that its key was not in the
   tree. If the key exists there is no such proof, so the insert raises `KeyError` and
   changes nothing.
10. **Not implemented** (not required by the task): delete, batch updates (Section 4.2),
    bulk loading, signatures, the ASB-tree and the EMB⁻/EMB* variants.
11. **Benchmark definitions.** Insert time includes the non-membership proof each
    insert builds. Read time = lookup only. Proof generation time = full `read()` /
    `read_range()` minus the lookup. Proof size = number of hashes (and bytes, 32 each),
    with the empty slots among them also counted separately; "total bytes" adds the
    records sent (answer and boundary records). The nesting information is not counted
    (the paper also leaves it out, Section 3.2).

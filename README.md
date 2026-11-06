# MB-tree and EMB-tree in Python

Author: Mohamed Adhil J

## What is this?

A data owner stores data on a server it does not fully trust. Clients ask the server
questions. **How can a client be sure the server's answer is genuine and complete?**

This repository implements two solutions from the paper by F. Li, M. Hadjieleftheriou,
G. Kollios and L. Reyzin, *Dynamic Authenticated Index Structures for Outsourced
Databases*, SIGMOD 2006 (Sections 3.2, 3.3, 4.2–4.3):

- **MB-tree (Merkle B-tree):** a B+ tree in which every node also has a hash, a
  fingerprint of everything below it. The owner publishes only the **root hash**.
- **EMB-tree (Embedded Merkle B-tree):** the same B+ tree, but inside every node the
  hashes form a small binary Merkle tree. This makes the proofs much shorter when nodes
  are big.

With every answer the server sends a short **proof**. The client rebuilds the root hash
from the answer and the proof. If it equals the trusted root hash, the answer is genuine;
if the server changed or left out anything, it does not match.

Both trees support:

| Operation | What the client gets |
|---|---|
| `insert(key, value)` | a proof that the key was not in the tree before |
| `read(key)` | the value + a proof (for a missing key: a proof that it is missing) |
| `read_range(low, high)` | all records in the range + a proof that none is changed or left out |
| `update(key, value)` | the root hash changes, so old answers no longer pass the check |

## Quick start

Only Python 3 is needed (standard library, nothing to install).
Tested with Python 3.12, 3.14 and 3.15 on Windows 11.

```
git clone https://github.com/immohamedadhil/mbtree-embtree.git
cd mbtree-embtree
```

| Command | What it does | Time |
|---|---|---|
| `python demo_toy16.py` | The 16-key example on both trees. Ends with "All checks passed" (exit code 0) | 1 s |
| `python -m unittest -v test_trees` | All 91 tests | about 40 s |
| `python benchmark.py` | Compares the two trees with 10,000 records (output: `benchmark_results.md`) | about 2 min |

## The demo: 16 keys

Keys 1 to 16 are inserted in order, with fanout 4 (at most 4 children per node) and,
for the EMB-tree, small-tree fanout f_k = 2. Both trees get the same shape:

```
root     [10]
inner    [4 | 7]  [13]
leaves   [1 2 3]  [4 5 6]  [7 8 9]  [10 11 12]  [13 14 15 16]
```

`python demo_toy16.py` then shows, on both trees, with every proof checked like a client would:

1. **Build the tree** and the two root hashes the owner publishes
2. **Read 14:** the answer and its proof (MB-tree 5 hashes, EMB-tree 6)
3. **Read the range 5 to 9:** the proof also shows 4 and 10, so nothing at the edges is left out
4. **Update 14:** the new answer is accepted, the old one is rejected
5. **Insert 17:** a proof that 17 is new; the last leaf splits
6. **Missing keys:** a proof for every place a missing key can fall
7. **A cheating server:** five kinds of lies, each one caught
8. **Same answers:** both trees always give the same answers; only the proofs differ

## Results

**Is it correct?** Yes. All 91 tests pass. Both trees always give the same answers.
Every honest proof is accepted, and every lie I tried (changed value, changed proof,
hidden record, false "not found") is caught.

**How was it measured?** 10,000 records in random order, the same data for both trees
(`python benchmark.py`).

### Proof size: how many hashes the server sends with one read (fewer is better)

| Node size (fanout) | MB-tree | EMB-tree |
|---:|---:|---:|
| 8 | 25 | 18 |
| 32 | 64 | 15 |
| 128 | 201 | 14 |

The MB-tree proof grows as nodes get bigger. The EMB-tree proof stays small.
(MB-tree numbers are averages over 1,000 reads, rounded; EMB-tree reads all have the same size.)

### Speed at fanout 32: microseconds per operation (smaller is faster)

| Operation | MB-tree | EMB-tree |
|---|---:|---:|
| Insert | 59 | 492 |
| Read: find the record | 2.5 | 2.7 |
| Read: make the proof | 8 | 26 |
| Read: check the proof (client) | 56 | 104 |
| Update | 36 | 90 |

Fanouts 8 and 128 show the same pattern. One exception: at fanout 128 the EMB-tree
checks read proofs faster (79 vs 120). Finding a record runs the same code in both
trees, so the small differences there are just noise.

### In one sentence

**The EMB-tree sends much smaller proofs, but it is slower to insert and update; the
MB-tree is faster, but its proofs grow with the node size.**

### Limitations

- Times change between runs on a laptop (up to about 2×); proof sizes are exact.
- Python and in memory, so the times can't be compared with the paper's.
- EMB-tree inserts rebuild the small trees inside the changed nodes, so they are slower
  than in the paper.
- With small nodes (fanout 4 and 8) the EMB-tree is not better; for range reads at
  fanout 8 its proof is even bigger, because of the empty slots.
- No delete and no signatures (not required by the task).

All the numbers (every fanout, range reads, bytes): [RESULTS.md](RESULTS.md) and
[benchmark_results.md](benchmark_results.md).

## Files

| File | What is in it |
|---|---|
| `mbtree.py` | The MB-tree: search, insert with node splits, update, and the proofs |
| `embtree.py` | The EMB-tree: the MB-tree with a small Merkle tree inside every node. It changes only four methods, all about one node: how it is hashed, how it is updated, and how it appears in a read proof and in a range proof |
| `hashing.py` | SHA-256 hashes of records and nodes |
| `verify.py` | The client side: `verify_read` and `verify_range`. It uses only the answer, the proof and the trusted root, never the tree |
| `demo_toy16.py` | The 16-key example |
| `test_trees.py` | 91 tests |
| `benchmark.py` | The benchmark; its latest output is `benchmark_results.md` |

## Using the trees in your own code

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

**Hashes.** A record's hash is H(0x00 ‖ record).
- MB-tree: a node's hash is H(0x01 ‖ h₁ ‖ … ‖ hₙ), one hash over all its entries.
- EMB-tree: a node's hash is the top of a small Merkle tree built over its entries,
  f_k at a time. Unused places are filled with an empty value E (see assumption 1).

**Read proof.** For every node on the path from the leaf to the root, the server sends
the hashes next to the path, as `[(left_hashes, right_hashes), ...]`, leaf first.
- MB-tree: the hashes of all the other entries of the node (up to f − 1 per node).
- EMB-tree: one step per level of the node's small tree, each with exactly f_k − 1 hashes.

**Range proof** (paper Figure 4). A copy of the tree in which everything the client does
not need is replaced by its hash. It shows the answer plus **one boundary record on each
side** (the largest key below `low` and the smallest key above `high`). Each node is a
list of hashes (`bytes`), records (`(key, value)`) and opened children (`list`). In the
EMB-tree the small-tree groups are nested the same way, so one checker works for both trees.

`verify_range` checks five things:
1. the root rebuilt from the proof equals the trusted root;
2. no hidden hash lies between two shown records;
3. the first shown record is below `low`, or nothing comes before it in the tree;
4. the same for the last shown record and `high`;
5. the answer is exactly the shown records inside [low, high].

**Missing key.** `read(key)` returns `(None, proof)`, where the proof is the range proof
for [key, key]. It shows the two neighbours of the key side by side, so the client sees
there is nothing between them. Every place a missing key can fall is tested on both trees
(`TestNonMembership`; keys 10, 20, …, 160; fanout 4, f_k = 2):

| Where the key falls | Example | Records shown |
|---|---|---|
| before every key | `read(5)` | 10 |
| after every key | `read(999)` | 160 |
| inside one leaf, inside one small-tree group | `read(15)` | 10, 20 |
| inside one leaf, between two small-tree groups (matters for the EMB-tree) | `read(25)` | 20, 30 |
| between two leaves with the same parent | `read(35)` | 30, 40 |
| between two leaves with different parents | `read(95)` | 90, 100 |
| the tree is empty | `read(5)` | none |

A key equal to a signpost is never missing: there is no delete, so every signpost is a
copy of a real key.

**Insert.** `insert(key, value)` first builds the missing-key proof for the new key, then
inserts, and returns that proof. It is checked against the root from *before* the insert.

**Update** (Sections 4.2–4.3). Only the record and the path up to the root are hashed
again; in the EMB-tree, only one path through each small tree on the way.

## Settings

| Setting | Meaning | Values used |
|---|---|---|
| `fanout` | Most entries per node (records in a leaf, children in an inner node); the EMB-tree's f_e. At least 3 | 16-key example: 4. Benchmark: 8, 32, 128 |
| `fk` | EMB-tree small-tree fanout f_k. At least 2 | 2 (the paper's default, Section 6.2) |
| Benchmark | 10,000 records in random order (seed 42); 1,000 reads, 1,000 updates, 200 range reads of 50 records; median of 5 runs | At the top of `benchmark.py` |

## Assumptions

1. **Nodes that are not full (EMB-tree):** empty places are filled with E (32 zero bytes),
   as suggested by the reviewer.
2. **EMB-tree inserts** rebuild the small trees of the changed nodes, so they are slower
   than in the paper.
3. **Hashes:** SHA-256 instead of SHA-1; records start with 0x00, nodes with 0x01.
4. **No signature:** the client gets the trusted root directly (as the task allows).
5. **In memory:** the fanout is set directly, the same for both trees.
6. **Keys** are unique integers, and **values** are text.
7. **Splits:** 5 entries become 3 + 2.
8. **Missing keys are proven,** and every insert proves its key is new (suggested by the
   reviewer).
9. **Not implemented:** delete, batch updates, signatures, and other variants (not required).

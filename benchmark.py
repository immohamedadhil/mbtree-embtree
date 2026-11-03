"""Benchmark: MB-tree vs EMB-tree on the same small, reproducible workload.

Run:  python benchmark.py      (the settings are at the top of this file)

Measured for each tree (README): insertion, read, update, proof generation and
verification time, and proof size.
- insert time:            includes the non-membership proof every insert builds first
- read time:              plain lookup, no proof (search / range_search)
- full read:              read() / read_range(): lookup + proof
- proof generation time:  full read - plain lookup, on the same keys
- times are microseconds per operation, the median over the repeats; the two
  trees take turns run by run. Expect run-to-run differences of tens of percent
  on a laptop: only large differences in time are meaningful. Proof sizes are exact.
- proof size: the hashes in the proof (count, and bytes at 32 each), how many of
  them are empty slots (EMPTY, EMB-tree only), and the total bytes sent = hash
  bytes + the records (answer and boundary records).
  Not counted: the nesting/position information (the paper also leaves it
  out, Section 3.2) and a signature (we do not sign the root).
"""
import gc
import platform
import random
import statistics
import time

from embtree import EMBTree
from hashing import EMPTY, HASH_SIZE, encode_record
from mbtree import MBTree
from verify import verify_range, verify_read

KEYS = 10_000            # records inserted, in random order
FANOUTS = [8, 32, 128]   # MB-tree fanout = EMB-tree external fanout f_e
FK = 2                   # EMB-tree embedded fanout f_k
REPEATS = 5              # runs per tree; the median time is reported
SEED = 42
N_READS = 1000           # random point reads (and as many updates)
N_RANGES = 200           # random range reads
RANGE_SIZE = 50          # records returned by each range read

ROWS = [
    ("insert", "Insert (per record, incl. its non-membership proof)"),
    ("read", "Read: lookup only"),
    ("read_full", "Read: full read() incl. proof"),
    ("read_proof", "Proof generation (read)"),
    ("read_verify", "Verification (read)"),
    ("range", "Range read: lookup only"),
    ("range_full", "Range read: full read_range() incl. proof"),
    ("range_proof", "Proof generation (range)"),
    ("range_verify", "Verification (range)"),
    ("update", "Update"),
]


def make_workload(n, seed):
    """The same keys and operations for both trees."""
    rng = random.Random(seed)
    keys = rng.sample(range(100 * n), n)  # inserted in this (random) order
    reads = rng.sample(keys, min(N_READS, n))
    updates = rng.sample(keys, min(N_READS, n))
    ordered = sorted(keys)
    size = min(RANGE_SIZE, n)
    ranges = []
    for _ in range(N_RANGES):
        s = rng.randrange(n - size + 1)
        ranges.append((ordered[s], ordered[s + size - 1]))  # each returns `size` records
    return keys, reads, ranges, updates


def per_op(start, count):
    """Microseconds per operation since `start`."""
    return (time.perf_counter() - start) / count * 1e6


def run_once(tree, workload):
    """One full run on a fresh tree. Returns (times, answers and proofs)."""
    keys, reads, ranges, updates = workload
    t = {}
    gc.disable()  # as timeit does: keeps garbage collection out of the timings

    start = time.perf_counter()
    for k in keys:
        tree.insert(k, f"value-{k}")
    t["insert"] = per_op(start, len(keys))
    root = tree.root_hash  # the trusted root the owner would publish

    start = time.perf_counter()
    for k in reads:
        tree.search(k)
    t["read"] = per_op(start, len(reads))

    read_answers, read_proofs = [], []
    start = time.perf_counter()
    for k in reads:
        value, proof = tree.read(k)
        read_answers.append(value)
        read_proofs.append(proof)
    t["read_full"] = per_op(start, len(reads))
    t["read_proof"] = t["read_full"] - t["read"]

    start = time.perf_counter()
    for k, value, proof in zip(reads, read_answers, read_proofs):
        assert verify_read(k, value, proof, root)
    t["read_verify"] = per_op(start, len(reads))

    start = time.perf_counter()
    for low, high in ranges:
        tree.range_search(low, high)
    t["range"] = per_op(start, len(ranges))

    range_answers, range_proofs = [], []
    start = time.perf_counter()
    for low, high in ranges:
        records, proof = tree.read_range(low, high)
        range_answers.append(records)
        range_proofs.append(proof)
    t["range_full"] = per_op(start, len(ranges))
    t["range_proof"] = t["range_full"] - t["range"]

    start = time.perf_counter()
    for (low, high), records, proof in zip(ranges, range_answers, range_proofs):
        assert verify_range(low, high, records, proof, root)
    t["range_verify"] = per_op(start, len(ranges))

    start = time.perf_counter()
    for k in updates:
        tree.update(k, f"value-{k}-new")
    t["update"] = per_op(start, len(updates))

    gc.enable()
    return t, (read_answers, read_proofs, range_answers, range_proofs)


def median_times(runs):
    times = {}
    for key, _ in ROWS:
        times[key] = statistics.median([t[key] for t, _ in runs])
    return times


# ---------- proof size ----------

def read_proof_hashes(proof):
    """Every hash in a read proof."""
    hashes = []
    for left, right in proof:
        hashes += left + right
    return hashes


def range_proof_items(node):
    """Every hash and record inside a range proof, in order."""
    items = []
    for x in node:
        if isinstance(x, list):
            items += range_proof_items(x)
        else:
            items.append(x)
    return items


def averages(rows):
    """rows of (hashes, empty slots, record bytes), one per proof ->
    the averages (hashes, empty slots, hash bytes, total bytes)."""
    n = len(rows)
    hashes = sum(r[0] for r in rows) / n
    empty = sum(r[1] for r in rows) / n
    record_bytes = sum(r[2] for r in rows) / n
    return hashes, empty, hashes * HASH_SIZE, hashes * HASH_SIZE + record_bytes


def proof_sizes(reads, results):
    """Average sizes of the read proofs and of the range proofs."""
    read_answers, read_proofs, _, range_proofs = results
    read_rows = []
    for k, value, proof in zip(reads, read_answers, read_proofs):
        hashes = read_proof_hashes(proof)
        read_rows.append((len(hashes), hashes.count(EMPTY), len(encode_record(k, value))))
    range_rows = []
    for proof in range_proofs:
        items = range_proof_items(proof)
        hashes = [x for x in items if isinstance(x, bytes)]
        record_bytes = sum(len(encode_record(x[0], x[1])) for x in items if isinstance(x, tuple))
        range_rows.append((len(hashes), hashes.count(EMPTY), record_bytes))
    return {"read": averages(read_rows), "range": averages(range_rows)}


# ---------- report ----------

def main():
    workload = make_workload(KEYS, SEED)
    reads = workload[1]
    range_size = min(RANGE_SIZE, KEYS)
    print("# Benchmark: MB-tree vs EMB-tree\n")
    print(f"- {KEYS:,} records inserted in random order (seed {SEED}); "
          f"{len(reads):,} reads, {N_RANGES} range reads of {range_size} records, {len(reads):,} updates")
    print(f"- times: microseconds per operation, median of {REPEATS} runs (the two trees take turns); "
          f"proof generation = full read - lookup only")
    print("- timings move by tens of percent between runs on a laptop, so only large differences "
          "mean something; proof sizes are exact")
    print(f"- Python {platform.python_version()} on {platform.platform()}\n")

    summary = []
    for fanout in FANOUTS:
        mb_runs, emb_runs = [], []
        for _ in range(REPEATS):  # alternate the trees, so a machine slowdown hits both alike
            mb, emb = MBTree(fanout), EMBTree(fanout, FK)
            mb_runs.append(run_once(mb, workload))
            emb_runs.append(run_once(emb, workload))
        mb_t, emb_t = median_times(mb_runs), median_times(emb_runs)
        mb_results, emb_results = mb_runs[-1][1], emb_runs[-1][1]
        assert mb_results[0] == emb_results[0], "the two trees gave different read answers"
        assert mb_results[2] == emb_results[2], "the two trees gave different range answers"
        mb_size, emb_size = proof_sizes(reads, mb_results), proof_sizes(reads, emb_results)

        print(f"## Fanout {fanout} (EMB-tree: f_e = {fanout}, f_k = {FK}, {emb.slots} slots per node); "
              f"tree height MB {mb.height}, EMB {emb.height}\n")
        print("| Measurement (µs per operation) | MB-tree | EMB-tree |")
        print("|---|---:|---:|")
        for key, label in ROWS:
            print(f"| {label} | {mb_t[key]:.1f} | {emb_t[key]:.1f} |")
        print("\n| Proof size (average) | MB-tree | EMB-tree |")
        print("|---|---:|---:|")
        for kind, label in (("read", "read"), ("range", f"range ({range_size} records + 2 boundary)")):
            mh, me, mb_bytes, mb_total = mb_size[kind]
            eh, ee, emb_bytes, emb_total = emb_size[kind]
            print(f"| {label}: hashes | {mh:.1f} | {eh:.1f} |")
            print(f"| {label}: of which empty slots (E) | {me:.1f} | {ee:.1f} |")
            print(f"| {label}: hash bytes | {mb_bytes:,.0f} | {emb_bytes:,.0f} |")
            print(f"| {label}: total bytes incl. records | {mb_total:,.0f} | {emb_total:,.0f} |")
        print("\nBoth trees gave identical answers; every proof was verified.\n")
        summary.append((fanout, mb_size["read"][0], emb_size["read"][0], emb_size["read"][1],
                        mb_size["range"][0], emb_size["range"][0], emb_size["range"][1]))

    print("## Summary: average hashes per proof (EMB-tree: of which empty slots)\n")
    print("| Fanout | Read: MB | Read: EMB | Range: MB | Range: EMB |")
    print("|---:|---:|---:|---:|---:|")
    for fanout, mr, er, ere, mg, eg, ege in summary:
        print(f"| {fanout} | {mr:.1f} | {er:.1f} ({ere:.1f} E) | {mg:.1f} | {eg:.1f} ({ege:.1f} E) |")


if __name__ == "__main__":
    main()

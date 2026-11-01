"""Benchmark: MB-tree vs EMB-tree on the same small, reproducible workload.

Run:  python benchmark.py
      python benchmark.py --keys 2000 --fanouts 8 32 --fk 2 --repeats 3

Measured for each tree (README): insertion, read, update, proof generation and
verification time, and proof size.
- read time:              plain lookup, no proof (search / range_search)
- full read:              read() / read_range(): lookup + proof
- proof generation time:  full read - plain lookup, on the same keys
- times are microseconds per operation, the median over the repeats; the two
  trees take turns run by run. Expect run-to-run differences of tens of percent
  on a laptop: only large differences in time are meaningful. Proof sizes are exact.
- proof size: the hashes in the proof (count, and bytes at 32 each), and the
  total bytes sent = hash bytes + the records (answer and boundary records).
  Not counted: the nesting/position information (the paper also leaves it
  out, Section 3.2) and a signature (we do not sign the root).
"""
import argparse
import gc
import platform
import random
import statistics
import time

from embtree import EMBTree
from hashing import HASH_SIZE, encode_record
from mbtree import MBTree
from verify import verify_range, verify_read

N_READS = 1000      # random point reads (and as many updates)
N_RANGES = 200      # random range reads
RANGE_SIZE = 50     # records returned by each range read


def make_workload(n, seed):
    """The same keys and operations for both trees."""
    rng = random.Random(seed)
    keys = rng.sample(range(100 * n), n)  # inserted in this (random) order
    reads = rng.sample(keys, min(N_READS, n))
    updates = rng.sample(keys, min(N_READS, n))
    ordered = sorted(keys)
    size = min(RANGE_SIZE, n)
    starts = [rng.randrange(n - size + 1) for _ in range(N_RANGES)]
    ranges = [(ordered[s], ordered[s + size - 1]) for s in starts]  # each returns `size` records
    return keys, reads, ranges, updates


def microseconds_per_op(loop, count):
    gc.disable()  # as timeit does: keeps garbage collection out of the timings
    start = time.perf_counter()
    loop()
    elapsed = time.perf_counter() - start
    gc.enable()
    return elapsed / count * 1e6


def run_once(make_tree, workload):
    """One full run on a fresh tree. Returns (times, answers, proofs, tree)."""
    keys, reads, ranges, updates = workload
    tree = make_tree()
    t = {}
    answers = {"read": [], "range": []}
    proofs = {"read": [], "range": []}

    def insert_all():
        for k in keys:
            tree.insert(k, f"value-{k}")

    def lookups():
        for k in reads:
            tree.search(k)

    def full_reads():
        for k in reads:
            value, proof = tree.read(k)
            answers["read"].append(value)
            proofs["read"].append(proof)

    def verify_reads():
        for k, value, proof in zip(reads, answers["read"], proofs["read"]):
            assert verify_read(k, value, proof, root)

    def range_lookups():
        for low, high in ranges:
            tree.range_search(low, high)

    def full_ranges():
        for low, high in ranges:
            records, proof = tree.read_range(low, high)
            answers["range"].append(records)
            proofs["range"].append(proof)

    def verify_ranges():
        for (low, high), records, proof in zip(ranges, answers["range"], proofs["range"]):
            assert verify_range(low, high, records, proof, root)

    def update_all():
        for k in updates:
            tree.update(k, f"value-{k}-new")

    t["insert"] = microseconds_per_op(insert_all, len(keys))
    root = tree.root_hash  # the trusted root the owner would publish
    t["read"] = microseconds_per_op(lookups, len(reads))
    t["read_full"] = microseconds_per_op(full_reads, len(reads))
    t["read_proof"] = t["read_full"] - t["read"]
    t["read_verify"] = microseconds_per_op(verify_reads, len(reads))
    t["range"] = microseconds_per_op(range_lookups, len(ranges))
    t["range_full"] = microseconds_per_op(full_ranges, len(ranges))
    t["range_proof"] = t["range_full"] - t["range"]
    t["range_verify"] = microseconds_per_op(verify_ranges, len(ranges))
    t["update"] = microseconds_per_op(update_all, len(updates))
    return t, answers, proofs, tree


# ---------- proof size ----------

def range_items(node):
    """Every hash and record inside a range proof."""
    for item in node:
        if isinstance(item, list):
            yield from range_items(item)
        else:
            yield item


def proof_sizes(reads, answers, proofs):
    """Average (hashes, hash bytes, total bytes) for the read proofs and the range proofs."""
    read_hashes, read_total = [], []
    for k, value, proof in zip(reads, answers["read"], proofs["read"]):
        n = sum(len(left) + len(right) for left, right in proof)
        read_hashes.append(n)
        read_total.append(n * HASH_SIZE + len(encode_record(k, value)))
    range_hashes, range_total = [], []
    for proof in proofs["range"]:
        items = list(range_items(proof))
        n = sum(isinstance(x, bytes) for x in items)
        record_bytes = sum(len(encode_record(*x)) for x in items if isinstance(x, tuple))
        range_hashes.append(n)
        range_total.append(n * HASH_SIZE + record_bytes)
    mean = statistics.mean
    return {
        "read": (mean(read_hashes), mean(read_hashes) * HASH_SIZE, mean(read_total)),
        "range": (mean(range_hashes), mean(range_hashes) * HASH_SIZE, mean(range_total)),
    }


# ---------- report ----------

ROWS = [
    ("insert", "Insert (per record)"),
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


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keys", type=int, default=10_000, help="records to insert (default 10000)")
    parser.add_argument("--fanouts", type=int, nargs="+", default=[8, 32, 128],
                        help="MB-tree fanout = EMB-tree external fanout (default 8 32 128)")
    parser.add_argument("--fk", type=int, default=2, help="EMB-tree embedded fanout (default 2)")
    parser.add_argument("--repeats", type=int, default=5, help="runs per tree; the median is reported")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    workload = make_workload(args.keys, args.seed)
    reads = workload[1]
    range_size = min(RANGE_SIZE, args.keys)
    print("# Benchmark: MB-tree vs EMB-tree\n")
    print(f"- {args.keys:,} records inserted in random order (seed {args.seed}); "
          f"{len(reads):,} reads, {N_RANGES} range reads of {range_size} records, {len(reads):,} updates")
    print(f"- times: microseconds per operation, median of {args.repeats} runs (the two trees take turns); "
          f"proof generation = full read - lookup only")
    print("- timings move by tens of percent between runs on a laptop, so only large differences "
          "mean something; proof sizes are exact")
    print(f"- Python {platform.python_version()} on {platform.platform()}\n")

    summary = []
    for fanout in args.fanouts:
        trees = {"MB-tree": lambda: MBTree(fanout),
                 "EMB-tree": lambda: EMBTree(fanout, args.fk)}
        runs = {name: [] for name in trees}
        for _ in range(args.repeats):
            for name, make_tree in trees.items():  # alternate the trees, so a machine slowdown hits both alike
                runs[name].append(run_once(make_tree, workload))
        result = {}
        for name in trees:
            times = {key: statistics.median(run[0][key] for run in runs[name]) for key, _ in ROWS}
            _, answers, proofs, tree = runs[name][-1]
            result[name] = (times, answers, proof_sizes(reads, answers, proofs), tree.height)
        (mb_t, mb_ans, mb_size, mb_h), (emb_t, emb_ans, emb_size, emb_h) = result.values()
        assert mb_ans == emb_ans, "the two trees gave different answers"

        print(f"## Fanout {fanout} (EMB-tree: f_e = {fanout}, f_k = {args.fk}); "
              f"tree height MB {mb_h}, EMB {emb_h}\n")
        print("| Measurement (µs per operation) | MB-tree | EMB-tree |")
        print("|---|---:|---:|")
        for key, label in ROWS:
            print(f"| {label} | {mb_t[key]:.1f} | {emb_t[key]:.1f} |")
        print("\n| Proof size (average) | MB-tree | EMB-tree |")
        print("|---|---:|---:|")
        for kind, label in (("read", "read"), ("range", f"range ({range_size} records + 2 boundary)")):
            mh, mb_bytes, mb_total = mb_size[kind]
            eh, emb_bytes, emb_total = emb_size[kind]
            print(f"| {label}: hashes | {mh:.1f} | {eh:.1f} |")
            print(f"| {label}: hash bytes | {mb_bytes:,.0f} | {emb_bytes:,.0f} |")
            print(f"| {label}: total bytes incl. records | {mb_total:,.0f} | {emb_total:,.0f} |")
        print("\nBoth trees gave identical answers; every proof was verified.\n")
        summary.append((fanout, mb_size["read"][0], emb_size["read"][0],
                        mb_size["range"][0], emb_size["range"][0]))

    print("## Summary: average hashes per proof\n")
    print("| Fanout | Read: MB | Read: EMB | Range: MB | Range: EMB |")
    print("|---:|---:|---:|---:|---:|")
    for fanout, mr, er, mg, eg in summary:
        print(f"| {fanout} | {mr:.1f} | {er:.1f} | {mg:.1f} | {eg:.1f} |")


if __name__ == "__main__":
    main()

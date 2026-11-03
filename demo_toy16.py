"""The 16-key toy example (from the email), on both trees.

Shows insert (with its non-membership proof), read, read_range and update,
and checks every proof the way a client would: with only the answer, the proof
and the owner's trusted root. It also shows every kind of missing-key proof and
that tampered answers are rejected.

Run:  python demo_toy16.py      (exit code 0 = every check passed)
"""
import sys

from embtree import EMBTree
from hashing import EMPTY, record_hash
from mbtree import MBTree
from verify import verify_range, verify_read

TOYS = ["ball", "car", "doll", "kite", "yo-yo", "puzzle", "drum", "train",
        "blocks", "teddy", "top", "whistle", "marbles", "jump rope", "rattle", "bubbles"]

failures = []


def check(label, ok):
    print(f"      {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok:
        failures.append(label)


def short(h):
    return "E" if h == EMPTY else h.hex()[:6]  # E = an empty slot (32 zero bytes)


def show_read_proof(proof):
    """One [left * right] group per step; * is where the client's own hash goes."""
    return " ".join("[" + " ".join([short(h) for h in left] + ["*"] + [short(h) for h in right]) + "]"
                    for left, right in proof)


def show_range_proof(node):
    if isinstance(node, bytes):
        return short(node)
    if isinstance(node, tuple):
        return str(node[0])  # a shown record, by its key
    return "[" + " ".join(show_range_proof(x) for x in node) + "]"


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


def size(hashes):
    """'6 hashes (2 of them E)' for a list of hashes."""
    empty = hashes.count(EMPTY)
    if empty:
        return f"{len(hashes)} hashes ({empty} of them E)"
    return f"{len(hashes)} hashes"


def hide_record(node, key):
    """Copy of a range proof with one shown record replaced by its (honest) hash."""
    if isinstance(node, tuple):
        if node[0] == key:
            return record_hash(node[0], node[1])
        return node
    if isinstance(node, list):
        return [hide_record(x, key) for x in node]
    return node


def print_shape(tree):
    for level in tree.levels():
        print("      " + " ".join(str(keys) for keys in level))


def section(title):
    print(f"\n=== {title} " + "=" * (70 - len(title)))


def main():
    trees = {"MB-tree  (fanout 4)": MBTree(4), "EMB-tree (fanout 4, f_k 2)": EMBTree(4, fk=2)}

    section("insert(1..16): keys in ascending order, toy names as values")
    proofs_ok = True
    for key, toy in enumerate(TOYS, start=1):
        for tree in trees.values():
            old_root = tree.root_hash
            proof = tree.insert(key, toy)   # first proves the key is new, then inserts
            proofs_ok &= verify_read(key, None, proof, old_root)
    check("all 32 inserts came with a valid non-membership proof", proofs_ok)
    mb, emb = trees.values()
    print("   B+ tree shape (the same for both trees):")
    print_shape(mb)
    check("both trees have the same shape", mb.levels() == emb.levels())
    roots = {}
    for name, tree in trees.items():
        roots[name] = tree.root_hash
        print(f"   {name}  root = {tree.root_hash.hex()[:16]}...   (the owner publishes this)")

    section("read(key): value + proof, checked against the trusted root")
    for key in (2, 14):
        for name, tree in trees.items():
            value, proof = tree.read(key)
            print(f"   {name}  read({key}) = {value!r}, {size(read_proof_hashes(proof))}: {show_read_proof(proof)}")
            check(f"client accepts read({key})", verify_read(key, value, proof, roots[name]))
    for name, tree in trees.items():
        value, proof = tree.read(99)
        print(f"   {name}  read(99) = {value!r} (not found); proof of absence: {show_range_proof(proof)}")
        check("client accepts that 99 is not in the tree", verify_read(99, None, proof, roots[name]))

    section("read_range(low, high): records + boundary records + hashes")
    for low, high in ((1, 5), (9, 12), (17, 20)):
        for name, tree in trees.items():
            records, proof = tree.read_range(low, high)
            hashes = [x for x in range_proof_items(proof) if isinstance(x, bytes)]
            print(f"   {name}  read_range({low}, {high}) -> keys {[k for k, _ in records]}, {size(hashes)}")
            print(f"      proof: {show_range_proof(proof)}")
            check(f"client accepts the range ({low}, {high}) as correct and complete",
                  verify_range(low, high, records, proof, roots[name]))

    section("update(5, 'robot'): only the path to the root is re-hashed")
    for name, tree in trees.items():
        old_value, old_proof = tree.read(5)
        tree.update(5, "robot")
        new_root = tree.root_hash
        value, proof = tree.read(5)
        print(f"   {name}  new root = {new_root.hex()[:16]}...   read(5) = {value!r}")
        check("new answer accepted with the new root", verify_read(5, value, proof, new_root))
        check("old answer ('yo-yo') rejected with the new root",
              not verify_read(5, old_value, old_proof, new_root))
        roots[name] = new_root

    section("insert(17, 'kazoo'): non-membership proof first, then the last leaf splits")
    for name, tree in trees.items():
        proof = tree.insert(17, "kazoo")
        check(f"{name}: proof that 17 was new, against the old root",
              verify_read(17, None, proof, roots[name]))
        roots[name] = tree.root_hash
        value, proof = tree.read(17)
        check(f"{name}: read(17) accepted", verify_read(17, value, proof, roots[name]))
    print("   new shape:")
    print_shape(mb)

    section("proof that a key is missing: every case (keys 10, 20, ..., 160)")
    cases = [("smaller than every key", 5), ("larger than every key", 999),
             ("same leaf, same small-tree group", 15), ("same leaf, different groups", 25),
             ("neighbouring leaves, same parent", 35), ("leaves under different parents", 95)]
    for name, tree_class in (("MB-tree", MBTree), ("EMB-tree", EMBTree)):   # fanout 4 (EMB-tree: f_k = 2)
        gapped = tree_class(4)
        for k in range(10, 170, 10):
            gapped.insert(k, f"v{k}")
        print(f"   {name}")
        for label, key in cases:
            value, proof = gapped.read(key)
            shown = [x[0] for x in range_proof_items(proof) if isinstance(x, tuple)]
            check(f"{label:34s} read({key}) = None, neighbours shown: {shown}",
                  value is None and verify_read(key, None, proof, gapped.root_hash))
        empty = tree_class(4)
        value, proof = empty.read(5)
        check("empty tree: read(5) = None", value is None and verify_read(5, None, proof, empty.root_hash))

    section("a cheating server is caught")
    for name, tree in trees.items():
        print(f"   {name}")
        value, proof = tree.read(2)
        check("value changed from 'car' to 'bike'", not verify_read(2, "bike", proof, roots[name]))
        bad = [(list(left), list(right)) for left, right in proof]
        side = bad[0][0] or bad[0][1]
        side[0] = bytes([side[0][0] ^ 1]) + side[0][1:]  # flip one bit of one proof hash
        check("one bit of one proof hash flipped", not verify_read(2, value, bad, roots[name]))
        _, absent = tree.read(99)
        check("'not found' claimed for key 2, which exists", not verify_read(2, None, absent, roots[name]))
        records, proof = tree.read_range(9, 12)
        check("record 10 hidden from read_range(9, 12)",
              not verify_range(9, 12, [r for r in records if r[0] != 10], hide_record(proof, 10), roots[name]))
        check("read_range answer with one record dropped",
              not verify_range(9, 12, records[1:], proof, roots[name]))

    section("both trees give identical answers")
    same_reads = all(mb.read(k)[0] == emb.read(k)[0] for k in range(-2, 20))
    same_ranges = all(mb.read_range(a, b)[0] == emb.read_range(a, b)[0]
                      for a in range(-2, 20) for b in range(a - 1, 20))
    check("read(k) for k = -2..19", same_reads)
    check("read_range(a, b) for all -2 <= a <= b+1 <= 20", same_ranges)

    print()
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()

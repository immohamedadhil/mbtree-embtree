"""The 16-key toy example (from the email), on both trees.

Shows insert, read, read_range and update, and checks every proof the way a
client would: with only the answer, the proof and the owner's trusted root.
It also shows that tampered answers are rejected.

Run:  python demo_toy16.py      (exit code 0 = every check passed)
"""
import sys

from embtree import EMBTree
from hashing import record_hash
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
    return h.hex()[:6]


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


def count_hashes(proof):
    if isinstance(proof, bytes):
        return 1
    if isinstance(proof, tuple) and len(proof) == 2 and isinstance(proof[0], list):
        return len(proof[0]) + len(proof[1])  # one step of a read proof
    if isinstance(proof, tuple):
        return 0  # a record
    return sum(count_hashes(x) for x in proof)


def hide_record(node, key):
    """Copy of a range proof with one shown record replaced by its (honest) hash."""
    if isinstance(node, tuple):
        return record_hash(*node) if node[0] == key else node
    if isinstance(node, list):
        return [hide_record(x, key) for x in node]
    return node


def section(title):
    print(f"\n=== {title} " + "=" * (70 - len(title)))


def main():
    trees = {"MB-tree  (fanout 4)": MBTree(4), "EMB-tree (fanout 4, f_k 2)": EMBTree(4, fk=2)}

    section("insert(1..16): keys in ascending order, toy names as values")
    for key, toy in enumerate(TOYS, start=1):
        for tree in trees.values():
            tree.insert(key, toy)
    mb, emb = trees.values()
    print("   B+ tree shape (the same for both trees):")
    for line in str(mb).splitlines():
        print("     ", line)
    check("both trees have the same shape", mb.levels() == emb.levels())
    roots = {}
    for name, tree in trees.items():
        roots[name] = tree.root_hash
        print(f"   {name}  root = {tree.root_hash.hex()[:16]}...   (the owner publishes this)")

    section("read(key): value + proof, checked against the trusted root")
    for key in (2, 14):
        for name, tree in trees.items():
            value, proof = tree.read(key)
            print(f"   {name}  read({key}) = {value!r}, {count_hashes(proof)} hashes: {show_read_proof(proof)}")
            check(f"client accepts read({key})", verify_read(key, value, proof, roots[name]))
    value, proof = mb.read(99)
    print(f"   read(99) on a missing key -> {value!r}, {proof!r} (not found)")

    section("read_range(low, high): records + boundary records + hashes")
    for low, high in ((1, 5), (9, 12), (17, 20)):
        for name, tree in trees.items():
            records, proof = tree.read_range(low, high)
            print(f"   {name}  read_range({low}, {high}) -> keys {[k for k, _ in records]}, "
                  f"{count_hashes(proof)} hashes")
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

    section("insert(17, 'kazoo'): the last leaf splits")
    for name, tree in trees.items():
        tree.insert(17, "kazoo")
        roots[name] = tree.root_hash
        value, proof = tree.read(17)
        check(f"{name}: read(17) accepted", verify_read(17, value, proof, roots[name]))
    print("   new shape:")
    for line in str(mb).splitlines():
        print("     ", line)

    section("a cheating server is caught")
    for name, tree in trees.items():
        print(f"   {name}")
        value, proof = tree.read(2)
        check("value changed from 'car' to 'bike'", not verify_read(2, "bike", proof, roots[name]))
        bad = [(list(left), list(right)) for left, right in proof]
        side = bad[0][0] or bad[0][1]
        side[0] = bytes([side[0][0] ^ 1]) + side[0][1:]  # flip one bit of one proof hash
        check("one bit of one proof hash flipped", not verify_read(2, value, bad, roots[name]))
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

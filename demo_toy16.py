"""The 16-key toy example (from the email), on both trees.

Builds the tree from keys 1..16, then shows read(14), read_range(5, 9),
update(14) and insert(17) (with its non-membership proof), and checks every
proof the way a client would: with only the answer, the proof and the owner's
trusted root. It also shows every kind of missing-key proof and that tampered
answers are rejected.

Run:  python demo_toy16.py      (exit code 0 = every check passed)
"""
import sys

from embtree import EMBTree
from hashing import EMPTY, record_hash
from mbtree import MBTree
from verify import verify_range, verify_read

TOYS = ["ball", "car", "doll", "kite", "yo-yo", "puzzle", "drum", "train",
        "blocks", "teddy", "top", "whistle", "marbles", "jump rope", "rattle", "bubbles"]

results = []  # every check, True or False


def mark(*checks):
    """Record one or more checks; return '[ok]' only if all of them passed."""
    results.extend(checks)
    return "[ok]" if all(checks) else "[FAIL]"


def section(number, title, what):
    print(f"\n{number}. {title}")
    print(f"   {what}\n")


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
    """'6 hashes (2 E)' for a list of hashes; E = an empty slot (32 zero bytes)."""
    empty = hashes.count(EMPTY)
    if empty:
        return f"{len(hashes)} hashes ({empty} E)"
    return f"{len(hashes)} hashes"


def shown_keys(proof):
    """The keys of the records a range proof shows."""
    return [x[0] for x in range_proof_items(proof) if isinstance(x, tuple)]


def hide_record(node, key):
    """Copy of a range proof with one shown record replaced by its (honest) hash."""
    if isinstance(node, tuple):
        if node[0] == key:
            return record_hash(node[0], node[1])
        return node
    if isinstance(node, list):
        return [hide_record(x, key) for x in node]
    return node


def caught(check):
    """Record one check that a lie was rejected."""
    results.append(check)
    return "caught" if check else "MISSED!"


def print_marks(rows, header):
    """A table of checks: one row per label, one mark for each tree."""
    print(f"   {header:48s} MB-tree  EMB-tree")
    for label, (mb_ok, emb_ok) in rows.items():
        print(f"   {label:48s} {mark(mb_ok):8s} {mark(emb_ok)}")


def print_shape(tree):
    levels = tree.levels()
    for depth, level in enumerate(levels):
        last = depth == len(levels) - 1
        name = "root" if depth == 0 else "leaves" if last else "inner"
        sep = " " if last else " | "  # leaves hold records, inner nodes hold signposts
        nodes = ["[" + sep.join(map(str, keys)) + "]" for keys in level]
        print(f"   {name:8s}  " + "  ".join(nodes))


def main():
    mb, emb = MBTree(4), EMBTree(4, fk=2)
    trees = {"MB-tree": mb, "EMB-tree": emb}
    line = "=" * 78
    print(line)
    print("  MB-tree vs EMB-tree: the 16-key toy example")
    print("  fanout 4, EMB small-tree fanout f_k = 2, keys 1..16 inserted in order")
    print("  Every answer is checked like a client would: answer + proof + trusted root.")
    print(line)

    # 1 ------------------------------------------------------------------
    section(1, "BUILD THE TREE", "Insert keys 1..16 into both trees.")
    for key, toy in enumerate(TOYS, start=1):
        for tree in trees.values():
            tree.insert(key, toy)
    print(f"   both trees have the same B+ tree shape   {mark(mb.levels() == emb.levels())}\n")
    print_shape(mb)
    roots = {name: tree.root_hash for name, tree in trees.items()}
    print("\n   Root hash published by the owner:")
    for name, root in roots.items():
        print(f"     {name:9s} {root.hex()[:16]}...")

    # 2 ------------------------------------------------------------------
    section(2, "READ 14", "The server sends the answer + a proof; the client checks it with the root.")
    print(f"   {'tree':9s} {'answer':10s} {'proof':15s} client")
    for name, tree in trees.items():
        value, proof = tree.read(14)
        flag = mark(verify_read(14, value, proof, roots[name]))
        print(f"   {name:9s} {value:10s} {size(read_proof_hashes(proof)):15s} {flag} accepted")

    # 3 ------------------------------------------------------------------
    section(3, "READ A RANGE: 5 to 9",
            "The proof also shows one boundary record on each side, so nothing is left out.")
    print(f"   {'tree':9s} {'answer':11s} {'shown':7s} {'proof':15s} client")
    for name, tree in trees.items():
        records, proof = tree.read_range(5, 9)
        flag = mark(verify_range(5, 9, records, proof, roots[name]))
        answer = " ".join(str(k) for k, _ in records)
        shown = shown_keys(proof)
        hashes = [x for x in range_proof_items(proof) if isinstance(x, bytes)]
        print(f"   {name:9s} {answer:11s} {f'{shown[0]}..{shown[-1]}':7s} {size(hashes):15s} "
              f"{flag} complete")

    # 4 ------------------------------------------------------------------
    section(4, "UPDATE 14",
            "Change key 14 from 'jump rope' to 'robot'. Only the path up to the root is re-hashed.")
    print(f"   {'tree':9s} {'new root':19s} {'new answer accepted':20s} old answer rejected")
    for name, tree in trees.items():
        old_value, old_proof = tree.read(14)
        tree.update(14, "robot")
        root = roots[name] = tree.root_hash
        value, proof = tree.read(14)
        new_ok = mark(value == "robot" and verify_read(14, value, proof, root))
        old_bad = mark(not verify_read(14, old_value, old_proof, root))
        print(f"   {name:9s} {root.hex()[:16]}... {new_ok:20s} {old_bad}")

    # 5 ------------------------------------------------------------------
    section(5, "INSERT 17", "First a proof that 17 is new; then 17 goes into the last leaf, which splits.")
    rows = {"proof that 17 was new (old root)": [], "read(17) is accepted (new root)": []}
    for name, tree in trees.items():
        proof = tree.insert(17, "kazoo")
        rows["proof that 17 was new (old root)"].append(verify_read(17, None, proof, roots[name]))
        roots[name] = tree.root_hash
        value, proof = tree.read(17)
        rows["read(17) is accepted (new root)"].append(verify_read(17, value, proof, roots[name]))
    print_marks(rows, "")
    print("\n   Leaf [13 14 15 16 17] is too full: it splits into [13 14 15] and [16 17],")
    print("   and 16 is copied up as a new signpost. The new shape:\n")
    print_shape(mb)

    # 6 ------------------------------------------------------------------
    section(6, "PROOF THAT A KEY IS MISSING",
            "A new tree with gaps (keys 10, 20, ..., 160). The proof shows the neighbours.")
    cases = [("smaller than every key", 5), ("larger than every key", 999),
             ("same leaf, same small-tree group", 15), ("same leaf, different groups", 25),
             ("neighbouring leaves, same parent", 35), ("leaves under different parents", 95)]
    gapped = []
    for tree_class in (MBTree, EMBTree):   # fanout 4 (EMB-tree: f_k = 2)
        tree = tree_class(4)
        for k in range(10, 170, 10):
            tree.insert(k, f"v{k}")
        gapped.append(tree)
    print(f"   {'where the key falls':34s} {'key':5s} {'shown':7s} MB-tree  EMB-tree")
    for label, key in cases:
        flags, shown = [], []
        for tree in gapped:
            value, proof = tree.read(key)
            shown.append(shown_keys(proof))
            flags.append(value is None and verify_read(key, None, proof, tree.root_hash))
        nb = " ".join(map(str, shown[0])) if shown[0] == shown[1] else f"{shown[0]} / {shown[1]}"
        print(f"   {label:34s} {key:<5d} {nb:7s} {mark(flags[0]):8s} {mark(flags[1])}")
    flags = []
    for tree_class in (MBTree, EMBTree):
        empty = tree_class(4)
        value, proof = empty.read(5)
        flags.append(value is None and verify_read(5, None, proof, empty.root_hash))
    print(f"   {'the tree is empty':34s} {5:<5d} {'-':7s} {mark(flags[0]):8s} {mark(flags[1])}")

    # 7 ------------------------------------------------------------------
    section(7, "A CHEATING SERVER IS CAUGHT",
            "The server lies. The client rebuilds the root from the answer + proof; it no\n"
            "   longer matches the trusted root, so the client rejects the answer.")
    lies = ["says key 14 is 'bike' (it is 'robot')",
            "changes one bit of one hash in the proof",
            "says key 14 is not found (it is there)",
            "hides record 7 from the range 5 to 9",
            "leaves record 5 out of the range 5 to 9"]
    rows = {lie: [] for lie in lies}
    for name, tree in trees.items():
        value, proof = tree.read(14)
        rows[lies[0]].append(not verify_read(14, "bike", proof, roots[name]))
        bad = [(list(left), list(right)) for left, right in proof]
        side = bad[0][0] or bad[0][1]
        side[0] = bytes([side[0][0] ^ 1]) + side[0][1:]  # flip one bit of one proof hash
        rows[lies[1]].append(not verify_read(14, value, bad, roots[name]))
        _, absent = tree.read(99)  # a real "not found" proof, sent for key 14
        rows[lies[2]].append(not verify_read(14, None, absent, roots[name]))
        records, proof = tree.read_range(5, 9)
        rows[lies[3]].append(not verify_range(
            5, 9, [r for r in records if r[0] != 7], hide_record(proof, 7), roots[name]))
        rows[lies[4]].append(not verify_range(5, 9, records[1:], proof, roots[name]))
    print(f"   {'the server...':44s} {'MB-tree':10s} EMB-tree")
    for lie, (mb_ok, emb_ok) in rows.items():
        print(f"   {lie:44s} {caught(mb_ok):10s} {caught(emb_ok)}")

    # 8 ------------------------------------------------------------------
    section(8, "BOTH TREES GIVE THE SAME ANSWERS",
            "The same question to both trees gives the same answer. Only the proofs differ.")

    def answer(tree, question):
        low, high = question
        if low == high:
            value = tree.read(low)[0]
            return "not found" if value is None else value
        return " ".join(str(k) for k, _ in tree.read_range(low, high)[0]) or "(none)"

    print(f"   {'question':20s} {'MB-tree answer':16s} {'EMB-tree answer':16s} same?")
    for low, high in ((14, 14), (99, 99), (5, 9), (15, 20)):
        question = f"read({low})" if low == high else f"read_range({low}, {high})"
        mb_ans, emb_ans = answer(mb, (low, high)), answer(emb, (low, high))
        print(f"   {question:20s} {mb_ans:16s} {emb_ans:16s} {mark(mb_ans == emb_ans)}")

    keys = range(-2, 20)  # keys 1..17 are in the tree; -2..0, 18, 19 are not
    reads = all(mb.read(k)[0] == emb.read(k)[0] for k in keys)
    ranges = all(mb.read_range(a, b)[0] == emb.read_range(a, b)[0]
                 for a in keys for b in keys if a <= b)
    print("\n   And not just these: every key from -2 to 19 (22 reads) and every range")
    print(f"   inside -2..19 (253 range reads) give the same answer on both trees.  {mark(reads, ranges)}")

    print("\n" + line)
    failed = results.count(False)
    if failed:
        print(f"  {failed} of {len(results)} checks FAILED")
        print(line)
        sys.exit(1)
    print(f"  All checks passed ({len(results)} checks).")
    print(line)


if __name__ == "__main__":
    main()

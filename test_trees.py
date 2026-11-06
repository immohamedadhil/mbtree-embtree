"""Tests. Run with:  python -m unittest -v test_trees"""
import copy
import itertools
import random
import unittest
from unittest.mock import patch

from embtree import EMBTree, build_small_tree, slots_for
from hashing import EMPTY, H, encode_record, node_hash, record_hash
from mbtree import Leaf, MBTree
from verify import verify_range, verify_read

# The 16-key toy example (email): key -> toy name.
TOY16 = {
    1: "ball", 2: "car", 3: "doll", 4: "kite",
    5: "yo-yo", 6: "puzzle", 7: "drum", 8: "train",
    9: "blocks", 10: "teddy", 11: "top", 12: "whistle",
    13: "marbles", 14: "jump rope", 15: "rattle", 16: "bubbles",
}


# ======================= checking helpers (they look inside the tree) =======================

def check_invariants(tree):
    """Fail if any B+ tree rule is broken."""
    if tree.size == 0:
        assert isinstance(tree.root, Leaf) and not tree.root.keys, "empty tree must be one empty leaf"
        return
    leaves = []
    check_node(tree, tree.root, 1, True, leaves)
    # The leaf links must visit exactly the leaves above, in the same order.
    assert leaves[-1].next is None, "last leaf must not link anywhere"
    for a, b in zip(leaves, leaves[1:]):
        assert a.next is b, "leaf links are broken"
    assert sum(len(leaf.keys) for leaf in leaves) == tree.size, "size counter is wrong"


def check_node(tree, node, depth, is_root, leaves):
    """Check one node's subtree (and collect its leaves); return its (smallest key, largest key)."""
    # Database System Concepts, 7th ed., Section 14.3 (n = fanout):
    # inner nodes ceil(n/2)..n children, leaves ceil((n-1)/2)..n-1 records.
    min_fill = (tree.fanout + 1) // 2      # ceil(n/2) children for non-root inner nodes
    min_leaf = tree.fanout // 2            # ceil((n-1)/2) records for non-root leaves
    assert node.keys == sorted(node.keys), "keys not sorted"
    assert len(set(node.keys)) == len(node.keys), "duplicate keys in a node"
    if isinstance(node, Leaf):
        assert len(node.keys) == len(node.values) == len(node.hashes), "keys/values/hashes length mismatch"
        assert len(node.keys) <= tree.fanout - 1, "leaf over-full"
        if not is_root:
            assert len(node.keys) >= min_leaf, "leaf under-full"
        assert depth == tree.height, "leaves not all at the same depth"
        leaves.append(node)
        return node.keys[0], node.keys[-1]
    n = len(node.children)
    assert len(node.keys) == n - 1, "inner node needs one fewer key than children"
    assert n <= tree.fanout, "inner node over-full"
    assert n >= (2 if is_root else min_fill), "inner node under-full"
    lo, hi = check_node(tree, node.children[0], depth + 1, False, leaves)
    smallest = lo
    for i, signpost in enumerate(node.keys):
        assert hi < signpost, "a key on the left is not smaller than its signpost"
        lo, hi = check_node(tree, node.children[i + 1], depth + 1, False, leaves)
        assert lo == signpost, "signpost is not the smallest key on its right"
    return smallest, hi


def check_hashes(tree):
    """Recompute every hash from the records alone; fail if any stored hash differs."""
    assert tree.root_hash == expected_hash(tree, tree.root), "root_hash is stale"


def expected_hash(tree, node):
    """The node's hash recomputed from the records below it, checked against what is stored."""
    if isinstance(node, Leaf):
        entries = [record_hash(k, v) for k, v in zip(node.keys, node.values)]
        assert node.hashes == entries, "stale record hash in a leaf"
    else:
        entries = [expected_hash(tree, child) for child in node.children]
    if isinstance(tree, EMBTree):
        small_tree = build_small_tree(entries, tree.fk, tree.slots)
        assert node.small_tree == small_tree, "stale hash in a node's small tree"
        digest = small_tree[-1][0]
    else:
        digest = node_hash(entries)
    assert node.digest == digest, "stale node hash"
    return digest


def check_authenticated(tree):
    """B+ rules every time. The full hash re-check re-hashes the whole tree, so on
    big trees it runs every 50th call (the *Hashes test classes re-check after
    every single operation)."""
    check_invariants(tree)
    if tree.size <= 100 or tree.size % 50 == 0:
        check_hashes(tree)


def count_hashing(operation):
    """Run operation(); return (record hashes computed, node hashes computed)."""
    with patch("mbtree.record_hash", wraps=record_hash) as rh, \
         patch("mbtree.node_hash", wraps=node_hash) as nh, \
         patch("embtree.node_hash", wraps=node_hash) as emb_nh:
        operation()
    return rh.call_count, nh.call_count + emb_nh.call_count


# ======================= B+ tree rules (on the MB-tree; again on the EMB-tree below) =======================

class TestBPlusTree(unittest.TestCase):
    tree_class = MBTree

    def check(self, tree):
        check_authenticated(tree)

    def build(self, items, fanout=4):
        """Insert items one by one, checking the tree after each insert."""
        tree = self.tree_class(fanout)
        for k, v in items:
            tree.insert(k, v)
            self.check(tree)
        return tree

    def test_toy16_shape(self):
        """Keys 1-16 in ascending order, fanout 4: the same tree as in my study notes."""
        tree = self.build(TOY16.items())
        self.assertEqual(tree.levels(), [
            [[7, 13]],
            [[3, 5], [9, 11], [15]],
            [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10], [11, 12], [13, 14], [15, 16]],
        ])
        self.assertEqual(tree.height, 3)
        for k, v in TOY16.items():
            self.assertEqual(tree.search(k), v)

    def test_toy_insert_17_to_23(self):
        """Continue the toy example to key 23: two splits in a row (worked out by hand earlier)."""
        tree = self.build(TOY16.items())
        for k in range(17, 24):
            tree.insert(k, f"toy-{k}")
            self.check(tree)
        self.assertEqual(tree.levels(), [
            [[7, 13, 19]],
            [[3, 5], [9, 11], [15, 17], [21]],
            [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10], [11, 12], [13, 14],
             [15, 16], [17, 18], [19, 20], [21, 22, 23]],
        ])

    def test_toy_range(self):
        tree = self.build(TOY16.items())
        self.assertEqual([k for k, _ in tree.range_search(1, 5)], [1, 2, 3, 4, 5])
        self.assertEqual([k for k, _ in tree.range_search(9, 12)], [9, 10, 11, 12])
        self.assertEqual(tree.range_search(14, 14), [(14, "jump rope")])

    def test_random_matches_dict(self):
        """Random inserts and updates: every answer must match a plain Python dict."""
        rng = random.Random(42)
        for fanout in (3, 4, 5, 8):
            with self.subTest(fanout=fanout):
                keys = rng.sample(range(10_000), 1000)
                truth = {k: f"value-{k}" for k in keys}
                tree = self.build(truth.items(), fanout)
                self.assertEqual(tree.size, len(truth))

                for k in rng.sample(keys, 200):  # change some values
                    truth[k] = f"value-{k}-u1"
                    tree.update(k, truth[k])
                self.check(tree)

                for k in range(-5, 10_005):  # every key, present or missing
                    self.assertEqual(tree.search(k), truth.get(k))

                ordered = sorted(truth.items())
                for _ in range(300):
                    low = rng.randint(-50, 10_050)
                    high = low + rng.randint(-10, 2000)  # includes some low > high cases
                    expected = [(k, v) for k, v in ordered if low <= k <= high]
                    self.assertEqual(tree.range_search(low, high), expected)

                for x in rng.sample(range(-50, 10_050), 300):  # neighbours used by range proofs
                    smaller = [k for k in truth if k < x]
                    larger = [k for k in truth if k > x]
                    self.assertEqual(tree._key_before(x), max(smaller) if smaller else None)
                    self.assertEqual(tree._key_after(x), min(larger) if larger else None)

    def test_range_edges(self):
        tree = self.build(TOY16.items())
        self.assertEqual(tree.range_search(-10, 0), [])     # entirely below the data
        self.assertEqual(tree.range_search(17, 99), [])     # entirely above the data
        self.assertEqual(tree.range_search(5, 4), [])       # low > high
        self.assertEqual(len(tree.range_search(-10, 99)), 16)  # everything

    def test_update_keeps_shape(self):
        tree = self.build(TOY16.items())
        before = tree.levels()
        tree.update(5, "robot")
        self.assertEqual(tree.search(5), "robot")
        self.assertEqual(tree.levels(), before)  # an update never changes the tree's shape
        self.check(tree)

    def test_errors(self):
        tree = self.build(TOY16.items())
        root = tree.root_hash
        with self.assertRaises(KeyError):
            tree.insert(7, "duplicate")              # A5: duplicate insert
        self.assertEqual(tree.search(7), "drum")     # ...and nothing changed
        self.assertEqual(tree.size, 16)
        self.assertEqual(tree.root_hash, root)
        with self.assertRaises(KeyError):
            tree.update(99, "nothing")               # A5: update of a missing key
        with self.assertRaises(TypeError):
            tree.insert("8", "text key")             # A8: keys are ints
        with self.assertRaises(TypeError):
            tree.insert(30, 123)                     # A8: values are text
        with self.assertRaises(ValueError):
            self.tree_class(fanout=2)                # A6: fanout must be at least 3
        with self.assertRaises(ValueError):
            tree.insert(10**5000, "v")               # too long to write as text: refused...
        with self.assertRaises(ValueError):
            tree.update(1, "\ud800")                 # not valid UTF-8 text: refused...
        self.check(tree)                             # ...and the tree is unchanged
        self.assertEqual((tree.size, tree.root_hash, tree.search(1)), (16, root, "ball"))
        for bad in ("5", 1.5, True):                 # A8: search/range also need int keys
            with self.assertRaises(TypeError):
                tree.search(bad)
            with self.assertRaises(TypeError):
                tree.range_search(bad, 10)
            with self.assertRaises(TypeError):
                tree.range_search(1, bad)
            with self.assertRaises(TypeError):
                self.tree_class().search(bad)        # same error on an empty tree

    def test_empty_tree(self):
        tree = self.tree_class()
        self.check(tree)
        self.assertIsNone(tree.search(1))
        self.assertEqual(tree.range_search(0, 100), [])
        with self.assertRaises(KeyError):
            tree.update(1, "x")

    def test_first_split(self):
        """Up to `fanout` - 1 records fit in the root leaf; one more splits it 2 + 2."""
        tree = self.build([(k, "v") for k in (1, 2, 3)])
        self.assertEqual((tree.levels(), tree.height), ([[[1, 2, 3]]], 1))
        tree.insert(4, "v")
        self.assertEqual((tree.levels(), tree.height), ([[[3]], [[1, 2], [3, 4]]], 2))

    def test_odd_splits_follow_the_textbook(self):
        """Database System Concepts 7th ed., Figures 14.16-14.17: a leaf keeps the first
        ceil(n/2) of its n records; an inner node keeps the first ceil((n+1)/2) of its
        n + 1 children and moves the key between the halves up (worked out by hand)."""
        tree = self.build([(k, "v") for k in range(1, 6)], fanout=5)    # 5 records -> 3 + 2
        self.assertEqual(tree.levels(), [[[4]], [[1, 2, 3], [4, 5]]])
        tree = self.build([(k, "v") for k in range(1, 4)], fanout=3)    # 3 records -> 2 + 1
        self.assertEqual(tree.levels(), [[[3]], [[1, 2], [3]]])
        tree = self.build([(k, "v") for k in range(1, 8)], fanout=3)    # root: 4 children -> 2 + 2
        self.assertEqual(tree.levels(), [[[5]], [[3], [7]], [[1, 2], [3, 4], [5, 6], [7]]])

    def test_every_insert_order(self):
        """All 5,040 insert orders of 7 keys give a valid tree with the right contents."""
        expected = [(k, f"v{k}") for k in range(7)]
        for fanout in (3, 4):
            for order in itertools.permutations(range(7)):
                tree = self.build([(k, f"v{k}") for k in order], fanout)
                self.assertEqual(tree.range_search(-1, 99), expected)

    def test_special_orders(self):
        """Descending and zig-zag orders also keep every rule."""
        descending = list(range(99, -1, -1))
        zigzag = [x for pair in zip(range(50), range(99, 49, -1)) for x in pair]  # 0, 99, 1, 98, ...
        for keys in (descending, zigzag):
            tree = self.build([(k, "v") for k in keys])
            self.assertEqual([k for k, _ in tree.range_search(0, 99)], list(range(100)))

    def test_unusual_keys_and_values(self):
        items = [(0, ""), (-5, "negative"), (2**70, "huge"), (-(2**70), "tiny"), (3, "café 🧸")]
        tree = self.build(items)
        self.assertEqual(tree.range_search(-(2**80), 2**80), sorted(items))

    def test_signposts_and_gaps(self):
        tree = self.build(TOY16.items())
        for k in (3, 5, 7, 9, 11, 13, 15):             # signpost keys are found in the right leaf
            self.assertEqual(tree.search(k), TOY16[k])
        with self.assertRaises(KeyError):
            tree.insert(7, "dup")                      # duplicate of a root signpost
        gap = self.build([(k, "v") for k in (10, 20, 30, 50, 60, 70, 80)])
        self.assertEqual(gap.levels()[-1], [[10, 20], [30, 50], [60, 70, 80]])
        # 55 goes to leaf [30 50] but is larger than all of it: the range must continue in the next leaf
        self.assertEqual([k for k, _ in gap.range_search(55, 60)], [60])
        self.assertEqual(gap.range_search(55, 55), [])
        self.assertIsNone(gap.search(55))


class TestHashing(unittest.TestCase):

    def test_sha256_known_answer(self):
        """SHA-256("abc") from the official test vectors (FIPS 180-2)."""
        self.assertEqual(H(b"abc").hex(),
                         "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_encoding_is_unambiguous(self):
        self.assertEqual(encode_record(353, "b"), b"\x00\x00\x00\x03" b"353" b"\x00\x00\x00\x01" b"b")
        # without the length fields both would be the text 123
        self.assertNotEqual(encode_record(1, "23"), encode_record(12, "3"))
        rng = random.Random(7)
        records = {(rng.randint(-2**70, 2**70), str(rng.randint(0, 99))) for _ in range(2000)}
        records |= {(k, v) for k in (-129, -128, -1, 0, 1, 127, 128, 255, 256) for v in ("", "a")}
        encodings = {encode_record(k, v) for k, v in records}
        self.assertEqual(len(encodings), len(records))  # no two records share bytes

    def test_labels_keep_records_and_nodes_apart(self):
        """A2: the same bytes hashed as a record and as a node give different hashes."""
        data = encode_record(1, "ball")
        self.assertEqual(record_hash(1, "ball"), H(b"\x00" + data))
        self.assertNotEqual(record_hash(1, "ball"), H(b"\x01" + data))


class TestMBTreeHashes(unittest.TestCase):

    def toy(self):
        tree = MBTree(4)
        for k, v in TOY16.items():
            tree.insert(k, v)
        return tree

    def test_toy16_root_by_hand(self):
        """The paper's formulas applied by hand to the known toy tree shape give the same root."""
        h = {k: record_hash(k, v) for k, v in TOY16.items()}
        L = {i: node_hash([h[2 * i - 1], h[2 * i]]) for i in range(1, 9)}  # L1 = [1 2] ... L8 = [15 16]
        A = node_hash([L[1], L[2], L[3]])
        B = node_hash([L[4], L[5], L[6]])
        C = node_hash([L[7], L[8]])
        self.assertEqual(self.toy().root_hash, node_hash([A, B, C]))

    def test_only_the_path_is_rehashed(self):
        """Paper Section 4.2: a change re-hashes one record and the nodes on its path, nothing else."""
        tree = self.toy()  # height 3
        self.assertEqual(count_hashing(lambda: tree.update(5, "robot")), (1, 3))  # L3, A, root
        self.assertEqual(count_hashing(lambda: tree.insert(0, "dice")), (1, 3))   # L1, A, root
        self.assertEqual(count_hashing(lambda: tree.insert(17, "kazoo")), (1, 3))  # L8, C, root
        # 18 splits L8 = [15 16 17]: L8, the new leaf, C, root
        self.assertEqual(count_hashing(lambda: tree.insert(18, "puzzle 2")), (1, 4))

    def test_hashes_fresh_after_every_operation(self):
        """Random inserts and updates; after every single one, all hashes are recomputed and compared."""
        rng = random.Random(3)
        for fanout in (3, 4, 5):
            tree = MBTree(fanout)
            keys = []
            for step in range(600):
                if keys and rng.random() < 0.4:
                    k = rng.choice(keys)
                    tree.update(k, f"value-{k}-u{step}")
                else:
                    k = rng.randint(0, 10**6)
                    if k in keys:
                        continue
                    tree.insert(k, f"value-{k}")
                    keys.append(k)
                check_invariants(tree)
                check_hashes(tree)

    def test_root_reacts_to_every_record(self):
        tree = self.toy()
        original = tree.root_hash
        roots = set()
        for k, v in TOY16.items():
            tree.update(k, v + "!")
            roots.add(tree.root_hash)
            tree.update(k, v)                      # change it back...
            self.assertEqual(tree.root_hash, original)  # ...and the old root returns
        self.assertEqual(len(roots), 16)           # each change gave its own new root
        self.assertNotIn(original, roots)

    def test_same_inserts_same_root(self):
        self.assertEqual(self.toy().root_hash, self.toy().root_hash)

    def test_empty_tree_root(self):
        self.assertEqual(MBTree().root_hash, node_hash([]))


def flip_bit(h, bit):
    """A copy of hash h with one bit flipped."""
    b = bytearray(h)
    b[bit // 8] ^= 1 << (bit % 8)
    return bytes(b)


def copy_proof(proof):
    return [(list(left), list(right)) for left, right in proof]


class TestMBTreeRead(unittest.TestCase):
    # proof size (number of hashes) for read(k) on the toy tree: (entries - 1) per node on the path
    # root [A B C]: 2, A and B: 2, C: 1, every leaf (2 records): 1
    TOY_PROOF_SIZES = {k: 5 if k <= 12 else 4 for k in range(1, 17)}

    def new_tree(self, fanout=4):
        return MBTree(fanout)

    def setUp(self):
        self.tree = self.new_tree(4)
        for k, v in TOY16.items():
            self.tree.insert(k, v)
        self.root = self.tree.root_hash  # the trusted root, as the owner would publish it

    def test_read_2_matches_hand_answer(self):
        """read(2) sends h1 | h_L2, h_L3 | h_B, h_C: exactly the 5 hashes worked out by hand."""
        value, proof = self.tree.read(2)
        self.assertEqual(value, "car")
        h = {k: record_hash(k, v) for k, v in TOY16.items()}
        L = {i: node_hash([h[2 * i - 1], h[2 * i]]) for i in range(1, 9)}
        B = node_hash([L[4], L[5], L[6]])
        C = node_hash([L[7], L[8]])
        self.assertEqual(proof, [
            ([h[1]], []),        # leaf L1 = [1 2]: record 2 is last
            ([], [L[2], L[3]]),  # node A: L1 is first, so nothing on the left
            ([], [B, C]),        # root: A is first
        ])
        self.assertTrue(verify_read(2, value, proof, self.root))

    def test_every_key_verifies(self):
        for k, v in TOY16.items():
            value, proof = self.tree.read(k)
            self.assertEqual(value, v)
            self.assertTrue(verify_read(k, value, proof, self.root))
            size = sum(len(left) + len(right) for left, right in proof)
            self.assertEqual(size, self.TOY_PROOF_SIZES[k])

    def test_random_trees_verify(self):
        rng = random.Random(11)
        for fanout in (3, 4, 5, 8, 32):
            tree = self.new_tree(fanout)
            keys = rng.sample(range(10**6), 500)
            for k in keys:
                tree.insert(k, f"value-{k}")
            for k in rng.sample(keys, 100):
                tree.update(k, f"value-{k}-u1")
            for k in keys:
                value, proof = tree.read(k)
                self.assertEqual(value, tree.search(k))
                self.assertTrue(verify_read(k, value, proof, tree.root_hash))

    def test_reject_false_not_found(self):
        """A server that says "not found" for a key that exists is caught, whatever proof it sends."""
        _, absent_proof = self.tree.read(99)  # a real proof that 99 is absent
        for k in TOY16:
            _, range_proof = self.tree.read_range(k, k)
            _, point_proof = self.tree.read(k)
            fake_proofs = {
                "honest range proof for [k, k]": range_proof,
                "range proof with record k hidden": hide(range_proof, k),
                "another key's absence proof": absent_proof,
                "the point proof for k": point_proof,
                "no proof": None,
            }
            for name, proof in fake_proofs.items():
                with self.subTest(key=k, fake=name):
                    self.assertFalse(verify_read(k, None, proof, self.root))

    # ----- tampering: every one of these must be rejected -----

    def test_reject_changed_value_or_key(self):
        value, proof = self.tree.read(2)
        self.assertFalse(verify_read(2, "robot", proof, self.root))   # server lies about the value
        self.assertFalse(verify_read(2, "car ", proof, self.root))    # even one extra space
        self.assertFalse(verify_read(3, value, proof, self.root))     # right value, wrong key
        v3, _ = self.tree.read(3)
        self.assertFalse(verify_read(3, v3, proof, self.root))        # real record 3, but 2's proof

    def test_reject_any_flipped_bit_in_proof(self):
        value, proof = self.tree.read(2)
        for level, (left, right) in enumerate(proof):
            for side, hashes in ((0, left), (1, right)):
                for j in range(len(hashes)):
                    for bit in range(256):
                        bad = copy_proof(proof)
                        bad[level][side][j] = flip_bit(hashes[j], bit)
                        self.assertFalse(verify_read(2, value, bad, self.root))

    def test_reject_changed_proof_shape(self):
        self.tree.insert(0, "dice")       # L1 = [0 1 2], so record 1 has a hash on each side
        self.root = self.tree.root_hash
        value, proof = self.tree.read(1)
        cases = {}
        bad = copy_proof(proof); bad[0] = (bad[0][1], bad[0][0]); cases["left and right swapped"] = bad
        bad = copy_proof(proof); bad[0] = ([], bad[0][0] + bad[0][1]); cases["record moved to first place"] = bad
        bad = copy_proof(proof); bad[1][1].pop(); cases["a hash removed"] = bad
        bad = copy_proof(proof); bad[1][1].append(bad[1][1][0]); cases["a hash added"] = bad
        bad = copy_proof(proof); bad.pop(); cases["root level removed"] = bad
        bad = copy_proof(proof); bad.append(([], [])); cases["extra level added"] = bad
        bad = copy_proof(proof); bad[0], bad[1] = bad[1], bad[0]; cases["levels in the wrong order"] = bad
        bad = copy_proof(proof); bad[0][0][0] = bad[0][0][0][:31]; cases["hash too short"] = bad
        bad = copy_proof(proof); bad[0][0][0] = "not bytes"; cases["hash of the wrong type"] = bad
        cases["no proof at all"] = None
        cases["empty proof"] = []
        for name, bad in cases.items():
            with self.subTest(name):
                self.assertFalse(verify_read(1, "ball", bad, self.root))

    def test_reject_wrong_root(self):
        value, proof = self.tree.read(2)
        self.assertFalse(verify_read(2, value, proof, flip_bit(self.root, 0)))
        self.assertFalse(verify_read(2, value, proof, b""))

    def test_old_proof_fails_after_update(self):
        """After an update the owner publishes a new root; old answers no longer verify."""
        old_value, old_proof = self.tree.read(5)
        self.tree.update(5, "robot")
        new_root = self.tree.root_hash
        self.assertFalse(verify_read(5, old_value, old_proof, new_root))  # stale answer replayed
        value, proof = self.tree.read(5)
        self.assertEqual(value, "robot")
        self.assertTrue(verify_read(5, value, proof, new_root))
        self.assertFalse(verify_read(5, value, proof, self.root))         # new answer vs old root
        # a record whose path did not change still has a valid proof, with a new sibling hash
        value, proof = self.tree.read(14)
        self.assertTrue(verify_read(14, value, proof, new_root))


def item_hash(item):
    """Hash of one range-proof item, computed independently of verify.py."""
    if isinstance(item, bytes):
        return item
    if isinstance(item, tuple):
        return record_hash(*item)
    return node_hash([item_hash(x) for x in item])


def positions(node, where=()):
    """Every position inside a range proof, as a tuple of list indices."""
    out = []
    for i in range(len(node)):
        out.append(where + (i,))
        if isinstance(node[i], list):
            out += positions(node[i], where + (i,))
    return out


def positions_items(proof):
    """Every item inside a range proof, in order."""
    return [get_at(proof, where) for where in positions(proof)]


def get_at(proof, where):
    for i in where:
        proof = proof[i]
    return proof


def hide(proof, key):
    """A copy of a range proof with the record for `key` replaced by its honest hash."""
    if isinstance(proof, tuple):
        return record_hash(*proof) if proof[0] == key else proof
    if isinstance(proof, list):
        return [hide(x, key) for x in proof]
    return proof


def deeply_nested(depth):
    proof = []
    for _ in range(depth):
        proof = [proof]
    return proof


def find_record(proof, key):
    """Position of the record with this key inside a range proof."""
    for where in positions(proof):
        item = get_at(proof, where)
        if isinstance(item, tuple) and item[0] == key:
            return where


def removed(proof, where):
    """A deep copy of `proof` with the item at `where` taken out."""
    bad = copy.deepcopy(proof)
    del get_at(bad, where[:-1])[where[-1]]
    return bad


def replaced(proof, where, new_item):
    """A deep copy of `proof` with the item at `where` replaced."""
    bad = copy.deepcopy(proof)
    get_at(bad, where[:-1])[where[-1]] = new_item
    return bad


class TestMBTreeRange(unittest.TestCase):

    def new_tree(self, fanout=4):
        return MBTree(fanout)

    def setUp(self):
        self.tree = self.new_tree(4)
        for k, v in TOY16.items():
            self.tree.insert(k, v)
        self.root = self.tree.root_hash
        h = {k: record_hash(k, v) for k, v in TOY16.items()}
        self.h = h
        self.L = {i: node_hash([h[2 * i - 1], h[2 * i]]) for i in range(1, 9)}  # L1 = [1 2] ... L8
        self.A = node_hash([self.L[1], self.L[2], self.L[3]])
        self.B = node_hash([self.L[4], self.L[5], self.L[6]])
        self.C = node_hash([self.L[7], self.L[8]])

    def rec(self, k):
        return (k, TOY16[k])

    def test_range_1_5_matches_hand_answer(self):
        """Records 1-5, right boundary 6, hashes h_B and h_C. No left boundary: 1 is first."""
        records, proof = self.tree.read_range(1, 5)
        self.assertEqual(records, [self.rec(k) for k in range(1, 6)])
        r = self.rec
        self.assertEqual(proof, [
            [[r(1), r(2)], [r(3), r(4)], [r(5), r(6)]],  # node A: all three leaves shown
            self.B,
            self.C,
        ])
        self.assertTrue(verify_range(1, 5, records, proof, self.root))

    def test_range_9_12_matches_hand_answer(self):
        """Boundaries 8 and 13; hashes h_A, h7, h14 and h_L8."""
        records, proof = self.tree.read_range(9, 12)
        self.assertEqual(records, [self.rec(k) for k in range(9, 13)])
        r, h, L = self.rec, self.h, self.L
        self.assertEqual(proof, [
            self.A,
            [[h[7], r(8)], [r(9), r(10)], [r(11), r(12)]],   # node B
            [[r(13), h[14]], L[8]],                          # node C
        ])
        self.assertTrue(verify_range(9, 12, records, proof, self.root))

    def test_edge_ranges(self):
        cases = [(-10, 0), (17, 99), (5, 4), (14, 14), (-10, 99), (1, 1), (16, 16), (0, 1), (16, 30),
                 (9, 5), (99, -10), (20, 17), (0, -5)]  # the last four: low > high, keys in between
        for low, high in cases:
            with self.subTest(low=low, high=high):
                records, proof = self.tree.read_range(low, high)
                self.assertEqual(records, self.tree.range_search(low, high))
                self.assertTrue(verify_range(low, high, records, proof, self.root))
        records, proof = self.tree.read_range(-10, 99)
        # everything is shown: the only hashes left are EMPTY slots (EMB-tree padding)
        self.assertTrue(all(x == EMPTY for x in positions_items(proof) if isinstance(x, bytes)))

    def test_random_ranges_verify(self):
        rng = random.Random(5)
        for fanout in (3, 4, 5, 8, 32):
            tree = self.new_tree(fanout)
            truth = {}
            for k in rng.sample(range(5000), 400):
                truth[k] = f"value-{k}"
                tree.insert(k, truth[k])
            ordered = sorted(truth.items())
            for _ in range(200):
                low = rng.randint(-100, 5100)
                high = low + rng.randint(-5, 600)
                records, proof = tree.read_range(low, high)
                self.assertEqual(records, [(k, v) for k, v in ordered if low <= k <= high])
                self.assertTrue(verify_range(low, high, records, proof, tree.root_hash))

    # ----- completeness attacks: the root still matches, so only the order checks can catch these -----

    def test_reject_hiding_any_record_or_subtree(self):
        """Replace any shown record or shown subtree by its own honest hash: always rejected."""
        rng = random.Random(9)
        trees = [self.tree]
        big = self.new_tree(3)
        for k in rng.sample(range(1000), 120):
            big.insert(k, f"value-{k}")
        trees.append(big)
        ranges = [(1, 5), (9, 12), (-10, 0), (17, 99), (14, 14), (5, 4), (-10, 99),
                  (100, 300), (0, 999), (500, 500)]
        for tree in trees:
            for low, high in ranges:
                records, proof = tree.read_range(low, high)
                for where in positions(proof):
                    item = get_at(proof, where)
                    if isinstance(item, bytes):
                        continue
                    bad = replaced(proof, where, item_hash(item))
                    self.assertEqual(item_hash(bad), tree.root_hash)  # root still matches...
                    self.assertFalse(verify_range(low, high, records, bad, tree.root_hash))  # ...but rejected
                    self.assertFalse(verify_range(low, high, [r for r in records if r != item],
                                                  bad, tree.root_hash))

    def test_reject_everything_hidden(self):
        """Showing no records at all ("the range is empty") is rejected for a non-empty tree."""
        _, proof = self.tree.read_range(1, 5)
        # root shown, every shown child replaced by its own honest hash
        fake = [item_hash(x) if isinstance(x, list) else x for x in proof]
        self.assertEqual(item_hash(fake), self.root)
        self.assertFalse(verify_range(1, 5, [], fake, self.root))

    def test_reject_changed_answer(self):
        records, proof = self.tree.read_range(9, 12)
        bad_answers = {
            "one record dropped": records[:1] + records[2:],
            "last record dropped": records[:-1],
            "nothing": [],
            "value changed": [records[0], (10, "robot")] + records[2:],
            "fake record added": records + [(12, "fake")],
            "wrong order": records[::-1],
            "boundary passed off as answer": [self.rec(8)] + records,
        }
        for name, bad in bad_answers.items():
            with self.subTest(name):
                self.assertFalse(verify_range(9, 12, bad, proof, self.root))

    def test_reject_changed_proof(self):
        records, proof = self.tree.read_range(9, 12)
        hash_positions = [w for w in positions(proof) if isinstance(get_at(proof, w), bytes)]
        first_hash = hash_positions[0]
        cases = {
            "record value changed": replaced(proof, find_record(proof, 11), (11, "robot")),
            "left boundary removed": removed(proof, find_record(proof, 8)),
            "right boundary removed": removed(proof, find_record(proof, 13)),
            "unknown item": replaced(proof, first_hash, 12345),
            "record with 3 parts": replaced(proof, find_record(proof, 10), (10, "teddy", "x")),
            "hash too short": replaced(proof, first_hash, get_at(proof, first_hash)[:31]),
            "root not a list": self.root,
            "no proof": None,
            "nested 5000 levels deep": deeply_nested(5000),
        }
        for name, bad in cases.items():
            with self.subTest(name):
                self.assertFalse(verify_range(9, 12, records, bad, self.root))
        for where in positions(proof):  # every bit of every hash in the proof
            item = get_at(proof, where)
            if isinstance(item, bytes):
                for bit in range(0, 256, 7):
                    bad = replaced(proof, where, flip_bit(item, bit))
                    self.assertFalse(verify_range(9, 12, records, bad, self.root))

    def test_reject_wrong_or_old_root(self):
        records, proof = self.tree.read_range(1, 5)
        self.assertFalse(verify_range(1, 5, records, proof, flip_bit(self.root, 3)))
        self.tree.update(3, "robot")
        self.assertFalse(verify_range(1, 5, records, proof, self.tree.root_hash))  # stale answer
        records, proof = self.tree.read_range(1, 5)
        self.assertTrue(verify_range(1, 5, records, proof, self.tree.root_hash))
        self.assertIn((3, "robot"), records)


# ======================= EMB-tree =======================

def emb_toy_hashes():
    """Every hash of the toy EMB-tree (fanout 4, f_k = 2), worked out by hand.
    Every node has 4 slots; empty slots are E (32 zero bytes); a group of only E is E.
    Names follow the study notes: a/b are the two groups of a node's small tree."""
    h = {k: record_hash(k, v) for k, v in TOY16.items()}
    n, E = node_hash, EMPTY
    x = dict(h=h, E=E)
    for leaf in range(1, 9):                      # L1 = [1 2 E E] ... L8 = [15 16 E E]
        x[f"aL{leaf}"] = n([h[2 * leaf - 1], h[2 * leaf]])
        x[f"L{leaf}"] = n([x[f"aL{leaf}"], E])    # its group (E E) is E
    x["aA"] = n([x["L1"], x["L2"]])
    x["bA"] = n([x["L3"], E])                     # A = [L1 L2 L3 E]
    x["A"] = n([x["aA"], x["bA"]])
    x["aB"] = n([x["L4"], x["L5"]])
    x["bB"] = n([x["L6"], E])                     # B = [L4 L5 L6 E]
    x["B"] = n([x["aB"], x["bB"]])
    x["aC"] = n([x["L7"], x["L8"]])
    x["C"] = n([x["aC"], E])                      # C = [L7 L8 E E]: its group (E E) is E
    x["aR"] = n([x["A"], x["B"]])
    x["bR"] = n([x["C"], E])                      # Root = [A B C E]
    x["root"] = n([x["aR"], x["bR"]])
    return x


class TestEMBTreeAsBPlusTree(TestBPlusTree):
    """Every B+ tree test again, on the EMB-tree (f_k = 2)."""
    tree_class = EMBTree


class TestEMBTreeHashes(unittest.TestCase):

    def toy(self):
        tree = EMBTree(4, fk=2)
        for k, v in TOY16.items():
            tree.insert(k, v)
        return tree

    def test_padding_rule(self):
        """Empty places are filled with EMPTY (32 zero bytes); every group is full."""
        h, E = [record_hash(k, "v") for k in range(5)], EMPTY
        self.assertEqual(E, bytes(32))
        self.assertEqual([slots_for(f, k) for f, k in ((4, 2), (5, 2), (32, 2), (128, 2), (8, 3))],
                         [4, 8, 32, 128, 9])
        self.assertIsNone(slots_for(4, 4))          # f_k >= f_e: no small tree
        a, b = node_hash(h[:2]), node_hash([h[2], E])
        self.assertEqual(build_small_tree(h[:3], 2, 4), [h[:3] + [E], [a, b], [node_hash([a, b])]])
        g = node_hash(h[:2])                        # a group of only EMPTY slots stays EMPTY
        self.assertEqual(build_small_tree(h[:2], 2, 4), [h[:2] + [E, E], [g, E], [node_hash([g, E])]])
        self.assertEqual(build_small_tree([], 2, 4), [[E] * 4, [E, E], [E]])   # an empty node is EMPTY
        self.assertEqual([len(level) for level in build_small_tree(h, 2, 8)], [8, 4, 2, 1])
        self.assertEqual(build_small_tree(h[:3], 4, None), [h[:3], [node_hash(h[:3])]])  # = MB-tree node

    def test_toy16_root_by_hand(self):
        self.assertEqual(self.toy().root_hash, emb_toy_hashes()["root"])

    def test_fk_too_small(self):
        with self.assertRaises(ValueError):
            EMBTree(4, fk=1)

    def test_update_rehashes_only_the_small_tree_paths(self):
        """Paper Section 4.3: update(5) re-hashes 1 record, then one path of 2 hashes in
        each small tree: L3, A and the root (every small tree has 2 levels)."""
        tree = self.toy()
        self.assertEqual(count_hashing(lambda: tree.update(5, "robot")), (1, 6))
        # insert rebuilds the small trees of the changed nodes: L1 = [0 1 2 E] (3),
        # A (3), root (3). Building the proof hashes nothing.
        self.assertEqual(count_hashing(lambda: tree.insert(0, "dice")), (1, 9))

    def test_hashes_fresh_after_every_operation(self):
        rng = random.Random(4)
        for fanout, fk in [(3, 2), (4, 2), (5, 2), (8, 3), (16, 4), (4, 4), (4, 9)]:
            with self.subTest(fanout=fanout, fk=fk):
                tree = EMBTree(fanout, fk)
                keys = []
                for step in range(400):
                    if keys and rng.random() < 0.4:
                        k = rng.choice(keys)
                        tree.update(k, f"value-{k}-u{step}")
                    else:
                        k = rng.randint(0, 10**6)
                        if k in keys:
                            continue
                        tree.insert(k, f"value-{k}")
                        keys.append(k)
                    check_invariants(tree)
                    check_hashes(tree)

    def test_same_as_mb_tree_when_fk_covers_the_node(self):
        """Paper Section 3.3: for f_k >= f_e the EMB-tree authenticates exactly like the MB-tree."""
        rng = random.Random(8)
        for fanout, fk in [(4, 4), (5, 7), (8, 8)]:
            mb, emb = MBTree(fanout), EMBTree(fanout, fk)
            keys = rng.sample(range(5000), 300)
            for k in keys:
                mb.insert(k, f"value-{k}")
                emb.insert(k, f"value-{k}")
                self.assertEqual(mb.root_hash, emb.root_hash)
            for k in rng.sample(keys, 50):
                mb.update(k, "changed")
                emb.update(k, "changed")
                self.assertEqual(mb.root_hash, emb.root_hash)
            for k in keys:
                self.assertEqual(mb.read(k), emb.read(k))
            for _ in range(50):
                low = rng.randint(-10, 5010)
                high = low + rng.randint(0, 400)
                self.assertEqual(mb.read_range(low, high), emb.read_range(low, high))


class TestEMBTreeRead(TestMBTreeRead):
    """All MB-tree read tests again on the EMB-tree (f_k = 2), plus its own hand-worked proofs."""
    # every small tree has 2 levels and every group is full: (f_k - 1) * 2 = 2 per node, 3 nodes
    TOY_PROOF_SIZES = {k: 6 for k in range(1, 17)}

    def new_tree(self, fanout=4):
        return EMBTree(fanout, fk=2)

    def test_read_2_matches_hand_answer(self):
        """h1, EMPTY, h_L2, b_A, h_B, b_R: 6 hashes worked out by hand."""
        x = emb_toy_hashes()
        value, proof = self.tree.read(2)
        self.assertEqual(proof, [
            ([x["h"][1]], []), ([], [x["E"]]),    # leaf L1: group [h1 h2], then [a E]
            ([], [x["L2"]]), ([], [x["bA"]]),     # node A: group [hL1 hL2], then [a b]
            ([], [x["B"]]), ([], [x["bR"]]),      # root: group [hA hB], then [a b]
        ])
        self.assertTrue(verify_read(2, value, proof, self.root))

    def test_read_4_matches_hand_answer(self):
        """h3, EMPTY, h_L1, b_A, h_B, b_R."""
        x = emb_toy_hashes()
        value, proof = self.tree.read(4)
        self.assertEqual(proof, [([x["h"][3]], []), ([], [x["E"]]),
                                 ([x["L1"]], []), ([], [x["bA"]]), ([], [x["B"]]), ([], [x["bR"]])])
        self.assertTrue(verify_read(4, value, proof, self.root))

    def test_read_14_matches_hand_answer(self):
        """h13, EMPTY, h_L8, EMPTY, EMPTY, a_R: leaf L7 and node C hold only 2 entries
        (each adds an EMPTY sibling), and C sits next to an empty slot in the root."""
        x = emb_toy_hashes()
        value, proof = self.tree.read(14)
        self.assertEqual(proof, [([x["h"][13]], []), ([], [x["E"]]), ([], [x["L8"]]), ([], [x["E"]]),
                                 ([], [x["E"]]), ([x["aR"]], [])])
        self.assertTrue(verify_read(14, value, proof, self.root))

    def test_random_trees_other_fk(self):
        rng = random.Random(12)
        for fanout, fk in [(5, 2), (8, 3), (16, 4), (32, 2), (4, 9)]:
            tree = EMBTree(fanout, fk)
            keys = rng.sample(range(10**6), 300)
            for k in keys:
                tree.insert(k, f"value-{k}")
            for k in keys:
                value, proof = tree.read(k)
                self.assertTrue(verify_read(k, value, proof, tree.root_hash))
                for left, right in proof:
                    if tree.slots is None:   # fk >= fanout: no small tree, an MB-tree node
                        self.assertLessEqual(len(left) + len(right), fanout - 1)
                    else:                    # padded small tree: every group is full
                        self.assertEqual(len(left) + len(right), fk - 1)


class TestEMBTreeRange(TestMBTreeRange):
    """All MB-tree range tests again on the EMB-tree (f_k = 2), plus its own hand-worked proofs."""

    def new_tree(self, fanout=4):
        return EMBTree(fanout, fk=2)

    def test_range_1_5_matches_hand_answer(self):
        """All of node A is shown (records 1-6); real hashes h_B and b_R; the E items are
        empty slots."""
        x, r, E = emb_toy_hashes(), self.rec, EMPTY
        records, proof = self.tree.read_range(1, 5)
        L1 = [[r(1), r(2)], E]
        L2 = [[r(3), r(4)], E]
        L3 = [[r(5), r(6)], E]
        A = [[L1, L2], [L3, E]]                         # A = [L1 L2 | L3 E]
        self.assertEqual(proof, [[A, x["B"]], x["bR"]])  # Root = [A B | C E]
        self.assertTrue(verify_range(1, 5, records, proof, self.root))

    def test_range_9_12_matches_hand_answer(self):
        """4 real hashes: h_A, h7, h14, h_L8 (as in the MB-tree), plus EMPTY slots."""
        x, r, E = emb_toy_hashes(), self.rec, EMPTY
        records, proof = self.tree.read_range(9, 12)
        L4 = [[x["h"][7], r(8)], E]
        L5 = [[r(9), r(10)], E]
        L6 = [[r(11), r(12)], E]
        B = [[L4, L5], [L6, E]]                         # B = [L4 L5 | L6 E]
        L7 = [[r(13), x["h"][14]], E]
        C = [[L7, x["L8"]], E]                          # C = [L7 L8 | E E]
        self.assertEqual(proof, [[x["A"], B], [C, E]])  # Root = [A B | C E]
        self.assertTrue(verify_range(9, 12, records, proof, self.root))

    def test_random_ranges_other_fk(self):
        rng = random.Random(13)
        for fanout, fk in [(5, 2), (8, 3), (16, 4), (4, 9)]:
            tree = EMBTree(fanout, fk)
            truth = {}
            for k in rng.sample(range(3000), 300):
                truth[k] = f"value-{k}"
                tree.insert(k, truth[k])
            ordered = sorted(truth.items())
            for _ in range(100):
                low = rng.randint(-50, 3050)
                high = low + rng.randint(-5, 400)
                records, proof = tree.read_range(low, high)
                self.assertEqual(records, [(k, v) for k, v in ordered if low <= k <= high])
                self.assertTrue(verify_range(low, high, records, proof, tree.root_hash))
                for where in positions(proof):  # hiding anything shown is still caught
                    item = get_at(proof, where)
                    if not isinstance(item, bytes) and rng.random() < 0.1:
                        bad = replaced(proof, where, item_hash(item))
                        self.assertFalse(verify_range(low, high, records, bad, tree.root_hash))


# ======================= both trees together =======================

def outcome(operation):
    """Run operation(); return ("ok", result) or ("error", the exception type)."""
    try:
        return "ok", operation()
    except (KeyError, TypeError, ValueError) as e:
        return "error", type(e)


class TestBothTreesAgree(unittest.TestCase):

    def test_identical_results_on_the_same_workload(self):
        """README: both trees return identical results after identical sequences of
        inserts, reads and updates. Every answer is also verified against each tree's own root."""
        rng = random.Random(21)
        for fanout, fk in [(4, 2), (5, 2), (8, 3), (16, 4)]:
            with self.subTest(fanout=fanout, fk=fk):
                mb, emb = MBTree(fanout), EMBTree(fanout, fk)
                truth = {}
                for step in range(1500):
                    op = rng.random()
                    key = rng.randint(0, 800)  # small key space: duplicates and misses happen
                    if op < 0.4:
                        value = f"value-{key}-s{step}"
                        mb_root, emb_root = mb.root_hash, emb.root_hash
                        a = outcome(lambda: mb.insert(key, value))
                        b = outcome(lambda: emb.insert(key, value))
                        self.assertEqual(a[0], b[0])
                        if a[0] == "ok":   # the returned non-membership proofs check out
                            self.assertTrue(verify_read(key, None, a[1], mb_root))
                            self.assertTrue(verify_read(key, None, b[1], emb_root))
                        else:
                            self.assertEqual(a, b)   # the same error on both trees
                        truth.setdefault(key, value)
                    elif op < 0.6:
                        value = f"value-{key}-u{step}"
                        a = outcome(lambda: mb.update(key, value))
                        b = outcome(lambda: emb.update(key, value))
                        self.assertEqual(a, b)
                        if key in truth:
                            truth[key] = value
                    elif op < 0.8:
                        (va, pa), (vb, pb) = mb.read(key), emb.read(key)
                        self.assertEqual(va, vb)
                        self.assertEqual(va, truth.get(key))
                        self.assertTrue(verify_read(key, va, pa, mb.root_hash))   # also "not found"
                        self.assertTrue(verify_read(key, vb, pb, emb.root_hash))
                    else:
                        low = rng.randint(-10, 810)
                        high = low + rng.randint(-5, 150)
                        (ra, pa), (rb, pb) = mb.read_range(low, high), emb.read_range(low, high)
                        self.assertEqual(ra, rb)
                        self.assertEqual(ra, sorted((k, v) for k, v in truth.items() if low <= k <= high))
                        self.assertTrue(verify_range(low, high, ra, pa, mb.root_hash))
                        self.assertTrue(verify_range(low, high, rb, pb, emb.root_hash))
                self.assertEqual(mb.levels(), emb.levels())  # same B+ tree shape underneath
                self.assertEqual(mb.size, len(truth))
                check_hashes(mb)
                check_hashes(emb)


# ======================= Kartick's feedback: non-membership =======================

def shown_keys(proof):
    """The keys of the records shown in a range / non-membership proof."""
    return [x[0] for x in positions_items(proof) if isinstance(x, tuple)]


class TestNonMembership(unittest.TestCase):
    """Every place where a missing key can be (keys 10, 20, ..., 170, fanout 4):
        Root [70|130]; [30|50], [90|110], [150];
        leaves [10 20] [30 40] [50 60] [70 80] [90 100] [110 120] [130 140] [150 160 170]"""
    CASES = {
        "smaller than every key": (5, [10]),
        "larger than every key": (999, [170]),
        "same leaf, same small-tree group": (15, [10, 20]),
        "same leaf, different small-tree groups": (165, [160, 170]),
        "neighbouring leaves with the same parent": (25, [20, 30]),
        "neighbouring leaves under different parents": (65, [60, 70]),
    }

    def trees(self):
        trees = [MBTree(4), EMBTree(4, fk=2)]
        for tree in trees:
            for k in range(10, 180, 10):
                tree.insert(k, f"v{k}")
        return trees

    def test_shape(self):
        for tree in self.trees():
            self.assertEqual(tree.levels(), [[[70, 130]], [[30, 50], [90, 110], [150]],
                                             [[10, 20], [30, 40], [50, 60], [70, 80], [90, 100],
                                              [110, 120], [130, 140], [150, 160, 170]]])

    def test_every_case_is_proven(self):
        for tree in self.trees():
            for name, (key, neighbours) in self.CASES.items():
                with self.subTest(tree=type(tree).__name__, case=name):
                    value, proof = tree.read(key)
                    self.assertIsNone(value)
                    self.assertTrue(verify_read(key, None, proof, tree.root_hash))
                    self.assertEqual(shown_keys(proof), neighbours)  # exactly the neighbours

    def test_empty_tree(self):
        for tree in (MBTree(4), EMBTree(4, fk=2)):
            value, proof = tree.read(5)
            self.assertIsNone(value)
            self.assertTrue(verify_read(5, None, proof, tree.root_hash))
            self.assertEqual(shown_keys(proof), [])

    def test_signpost_keys_are_members(self):
        """Without delete every signpost is a real key, so it is never a non-membership case."""
        for tree in self.trees():
            for k in (30, 50, 70, 90, 110, 130, 150):   # every signpost of the gapped tree
                value, proof = tree.read(k)
                self.assertEqual(value, f"v{k}")
                self.assertFalse(verify_read(k, None, proof, tree.root_hash))

    def test_false_non_membership_rejected(self):
        """For a key that exists, no proof convinces the client that it is missing."""
        for tree in self.trees():
            for k in range(10, 180, 10):
                for other in (5, 95, 999):
                    _, proof = tree.read(other)   # a real non-membership proof, for another key
                    self.assertFalse(verify_read(k, None, proof, tree.root_hash))
                _, proof = tree.read_range(k, k)  # the honest range proof shows k itself
                self.assertFalse(verify_read(k, None, proof, tree.root_hash))


class TestInsertProof(unittest.TestCase):
    """insert() first proves the key is not in the tree yet (non-membership proof)."""

    def test_every_insert_returns_a_valid_proof(self):
        rng = random.Random(31)
        for tree in (MBTree(4), EMBTree(4, fk=2), MBTree(8), EMBTree(8, fk=2)):
            for k in rng.sample(range(10_000), 300):
                old_root = tree.root_hash
                proof = tree.insert(k, f"v{k}")
                self.assertTrue(verify_read(k, None, proof, old_root))        # absent before
                self.assertFalse(verify_read(k, None, proof, tree.root_hash))  # not after


class TestEmptySlots(unittest.TestCase):
    """EMPTY slots are skipped by the completeness check, so make sure a server cannot
    use them to hide anything."""

    def setUp(self):
        self.tree = EMBTree(4, fk=2)
        for k, v in TOY16.items():
            self.tree.insert(k, v)
        self.root = self.tree.root_hash

    def test_cannot_hide_with_empty(self):
        records, proof = self.tree.read_range(9, 12)
        for where in positions(proof):
            item = get_at(proof, where)
            if item == EMPTY:
                continue
            bad = replaced(proof, where, EMPTY)   # a record, a hash or a subtree becomes "empty"
            self.assertFalse(verify_range(9, 12, records, bad, self.root))
            self.assertFalse(verify_range(9, 12, [r for r in records if r != item], bad, self.root))

    def test_cannot_add_or_remove_empty(self):
        records, proof = self.tree.read_range(9, 12)
        for where in positions(proof):
            if get_at(proof, where) == EMPTY:
                self.assertFalse(verify_range(9, 12, records, removed(proof, where), self.root))
            bad = copy.deepcopy(proof)
            (get_at(bad, where[:-1]) if len(where) > 1 else bad).insert(where[-1], EMPTY)
            self.assertFalse(verify_range(9, 12, records, bad, self.root))

    def test_mb_proofs_do_not_accept_empty(self):
        mb = MBTree(4)
        for k, v in TOY16.items():
            mb.insert(k, v)
        records, proof = mb.read_range(9, 12)
        bad = copy.deepcopy(proof)
        bad[1].append(EMPTY)                       # node B, which is shown
        self.assertFalse(verify_range(9, 12, records, bad, mb.root_hash))


if __name__ == "__main__":
    unittest.main()

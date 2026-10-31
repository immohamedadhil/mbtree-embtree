"""Tests. Run with:  python -m unittest -v test_trees"""
import copy
import itertools
import random
import unittest
from unittest.mock import patch

from bptree import BPlusTree
from hashing import H, encode_record, node_hash, record_hash
from mbtree import MBTree
from verify import verify_range, verify_read

# The 16-key toy example (email): key -> toy name.
TOY16 = {
    1: "ball", 2: "car", 3: "doll", 4: "kite",
    5: "yo-yo", 6: "puzzle", 7: "drum", 8: "train",
    9: "blocks", 10: "teddy", 11: "top", 12: "whistle",
    13: "marbles", 14: "jump rope", 15: "rattle", 16: "bubbles",
}


class TestBPlusTree(unittest.TestCase):
    tree_class = BPlusTree

    def check(self, tree):
        tree.check_invariants()

    def build(self, items, fanout=4):
        """Insert items one by one, checking the tree after each insert."""
        tree = self.tree_class(fanout)
        for k, v in items:
            tree.insert(k, v)
            self.check(tree)
        return tree

    def test_toy16_shape(self):
        """Keys 1-16 in ascending order, fanout 4: the same tree as in our study notes."""
        tree = self.build(TOY16.items())
        self.assertEqual(tree.levels(), [
            [[10]],
            [[4, 7], [13]],
            [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12], [13, 14, 15, 16]],
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
            [[10, 19]],
            [[4, 7], [13, 16], [22]],
            [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12], [13, 14, 15],
             [16, 17, 18], [19, 20, 21], [22, 23]],
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
                self.assertEqual(len(tree), len(truth))

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
        with self.assertRaises(KeyError):
            tree.insert(7, "duplicate")              # A5: duplicate insert
        self.assertEqual(tree.search(7), "drum")     # ...and nothing changed
        self.assertEqual(len(tree), 16)
        with self.assertRaises(KeyError):
            tree.update(99, "nothing")               # A5: update of a missing key
        with self.assertRaises(TypeError):
            tree.insert("8", "text key")             # A8: keys are ints
        with self.assertRaises(TypeError):
            tree.insert(30, 123)                     # A8: values are text
        with self.assertRaises(ValueError):
            self.tree_class(fanout=2)                # A6: fanout must be at least 3
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
        """Up to `fanout` records fit in the root leaf; one more splits it 3 + 2."""
        tree = self.build([(k, "v") for k in (1, 2, 3, 4)])
        self.assertEqual((tree.levels(), tree.height), ([[[1, 2, 3, 4]]], 1))
        tree.insert(5, "v")
        self.assertEqual((tree.levels(), tree.height), ([[[4]], [[1, 2, 3], [4, 5]]], 2))

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
        for k in (4, 7, 10, 13):                       # signpost keys are found in the right leaf
            self.assertEqual(tree.search(k), TOY16[k])
        with self.assertRaises(KeyError):
            tree.insert(10, "dup")                     # duplicate of the root signpost
        gap = self.build([(k, "v") for k in (1, 2, 3, 5, 6, 7, 8)])  # leaves [1 2 3] [5 6 7 8]
        self.assertEqual([k for k, _ in gap.range_search(4, 5)], [5])  # low is missing and past its leaf's end
        self.assertEqual(gap.range_search(4, 4), [])
        self.assertIsNone(gap.search(4))


class TestHashing(unittest.TestCase):

    def test_sha256_known_answer(self):
        """SHA-256("abc") from the official test vectors (FIPS 180-2)."""
        self.assertEqual(H(b"abc").hex(),
                         "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_encoding_is_unambiguous(self):
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


class TestMBTreeAsBPlusTree(TestBPlusTree):
    """Every B+ tree test again, on the MB-tree, also re-checking all hashes after each insert."""
    tree_class = MBTree

    def check(self, tree):
        tree.check_invariants()
        tree.check_hashes()


class TestMBTreeHashes(unittest.TestCase):

    def toy(self):
        tree = MBTree(4)
        for k, v in TOY16.items():
            tree.insert(k, v)
        return tree

    def test_toy16_root_by_hand(self):
        """The paper's formulas applied by hand to the known toy tree shape give the same root."""
        h = {k: record_hash(k, v) for k, v in TOY16.items()}
        L1 = node_hash([h[1], h[2], h[3]])
        L2 = node_hash([h[4], h[5], h[6]])
        L3 = node_hash([h[7], h[8], h[9]])
        L4 = node_hash([h[10], h[11], h[12]])
        L5 = node_hash([h[13], h[14], h[15], h[16]])
        A = node_hash([L1, L2, L3])
        B = node_hash([L4, L5])
        self.assertEqual(self.toy().root_hash, node_hash([A, B]))

    def count_hashing(self, operation):
        """Run operation(); return (record hashes computed, node hashes computed)."""
        with patch("mbtree.record_hash", wraps=record_hash) as rh, \
             patch("mbtree.node_hash", wraps=node_hash) as nh:
            operation()
        return rh.call_count, nh.call_count

    def test_only_the_path_is_rehashed(self):
        """Paper Section 4.2: a change re-hashes one record and the nodes on its path, nothing else."""
        tree = self.toy()  # height 3
        self.assertEqual(self.count_hashing(lambda: tree.update(5, "robot")), (1, 3))  # L2, A, root
        self.assertEqual(self.count_hashing(lambda: tree.insert(0, "dice")), (1, 3))   # L1, A, root
        # 17 splits L5: L5, the new leaf, B, root
        self.assertEqual(self.count_hashing(lambda: tree.insert(17, "kazoo")), (1, 4))

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
                tree.check_invariants()
                tree.check_hashes()

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

    def setUp(self):
        self.tree = MBTree(4)
        for k, v in TOY16.items():
            self.tree.insert(k, v)
        self.root = self.tree.root_hash  # the trusted root, as the owner would publish it

    def test_read_2_matches_hand_answer(self):
        """read(2) sends h1, h3 | h_L2, h_L3 | h_B: exactly the 5 hashes worked out by hand."""
        value, proof = self.tree.read(2)
        self.assertEqual(value, "car")
        h = {k: record_hash(k, v) for k, v in TOY16.items()}
        L2 = node_hash([h[4], h[5], h[6]])
        L3 = node_hash([h[7], h[8], h[9]])
        B = node_hash([node_hash([h[10], h[11], h[12]]), node_hash([h[13], h[14], h[15], h[16]])])
        self.assertEqual(proof, [
            ([h[1]], [h[3]]),   # leaf L1: left and right of record 2
            ([], [L2, L3]),     # node A: L1 is first, so nothing on the left
            ([], [B]),          # root: A is first
        ])
        self.assertTrue(verify_read(2, value, proof, self.root))

    def test_every_key_verifies(self):
        for k, v in TOY16.items():
            value, proof = self.tree.read(k)
            self.assertEqual(value, v)
            self.assertTrue(verify_read(k, value, proof, self.root))
            # (number of entries - 1) hashes per node on the path
            expected = sum(len(left) + len(right) for left, right in proof)
            self.assertEqual(expected, {1: 5, 2: 5, 3: 5, 4: 5, 5: 5, 6: 5, 7: 5, 8: 5, 9: 5,
                                        10: 4, 11: 4, 12: 4, 13: 5, 14: 5, 15: 5, 16: 5}[k])

    def test_random_trees_verify(self):
        rng = random.Random(11)
        for fanout in (3, 4, 5, 8, 32):
            tree = MBTree(fanout)
            keys = rng.sample(range(10**6), 500)
            for k in keys:
                tree.insert(k, f"value-{k}")
            for k in rng.sample(keys, 100):
                tree.update(k, f"value-{k}-u1")
            for k in keys:
                value, proof = tree.read(k)
                self.assertEqual(value, tree.search(k))
                self.assertTrue(verify_read(k, value, proof, tree.root_hash))
                self.assertEqual(len(proof), tree.height)  # one step per level

    def test_missing_key(self):
        self.assertEqual(self.tree.read(99), (None, None))  # A4: "not found", no proof
        self.assertEqual(MBTree().read(1), (None, None))

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
        value, proof = self.tree.read(5)  # middle of L2: [h4] | [h6]
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
                self.assertFalse(verify_read(5, "yo-yo", bad, self.root))

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
    for i, item in enumerate(node):
        yield where + (i,)
        if isinstance(item, list):
            yield from positions(item, where + (i,))


def positions_items(proof):
    """Every item inside a range proof, in order."""
    return [get_at(proof, where) for where in positions(proof)]


def get_at(proof, where):
    for i in where:
        proof = proof[i]
    return proof


def replaced(proof, where, new_item):
    """A deep copy of `proof` with the item at `where` replaced."""
    bad = copy.deepcopy(proof)
    get_at(bad, where[:-1])[where[-1]] = new_item
    return bad


class TestMBTreeRange(unittest.TestCase):

    def setUp(self):
        self.tree = MBTree(4)
        for k, v in TOY16.items():
            self.tree.insert(k, v)
        self.root = self.tree.root_hash
        h = {k: record_hash(k, v) for k, v in TOY16.items()}
        self.h = h
        self.L = {1: node_hash([h[1], h[2], h[3]]), 2: node_hash([h[4], h[5], h[6]]),
                  3: node_hash([h[7], h[8], h[9]]), 4: node_hash([h[10], h[11], h[12]]),
                  5: node_hash([h[13], h[14], h[15], h[16]])}
        self.B = node_hash([self.L[4], self.L[5]])

    def rec(self, k):
        return (k, TOY16[k])

    def test_range_1_5_matches_hand_answer(self):
        """Records 1-5, right boundary 6, hashes h_L3 and h_B. No left boundary: 1 is first."""
        records, proof = self.tree.read_range(1, 5)
        self.assertEqual(records, [self.rec(k) for k in range(1, 6)])
        r = self.rec
        self.assertEqual(proof, [
            [[r(1), r(2), r(3)], [r(4), r(5), r(6)], self.L[3]],  # node A
            self.B,
        ])
        self.assertTrue(verify_range(1, 5, records, proof, self.root))

    def test_range_9_12_matches_hand_answer(self):
        """Boundaries 8 and 13; hashes h_L1, h_L2, h7 and h14, h15, h16 (and NOT h_L4)."""
        records, proof = self.tree.read_range(9, 12)
        self.assertEqual(records, [self.rec(k) for k in range(9, 13)])
        r, h, L = self.rec, self.h, self.L
        self.assertEqual(proof, [
            [L[1], L[2], [h[7], r(8), r(9)]],                        # node A
            [[r(10), r(11), r(12)], [r(13), h[14], h[15], h[16]]],   # node B
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
        self.assertFalse(any(isinstance(x, bytes) for x in positions_items(proof)))  # all shown

    def test_missing_key_proven_absent(self):
        """A range over a gap returns nothing, and the proof shows the neighbours 3 and 5."""
        gap = MBTree(4)
        for k in (1, 2, 3, 5, 6, 7, 8):
            gap.insert(k, f"v{k}")
        records, proof = gap.read_range(4, 4)
        self.assertEqual(records, [])
        self.assertTrue(verify_range(4, 4, [], proof, gap.root_hash))
        shown = [x for x in positions_items(proof) if isinstance(x, tuple)]
        self.assertEqual(shown, [(3, "v3"), (5, "v5")])

    def test_empty_tree(self):
        tree = MBTree()
        records, proof = tree.read_range(0, 10)
        self.assertEqual((records, proof), ([], []))
        self.assertTrue(verify_range(0, 10, [], proof, tree.root_hash))

    def test_random_ranges_verify(self):
        rng = random.Random(5)
        for fanout in (3, 4, 5, 8, 32):
            tree = MBTree(fanout)
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
        big = MBTree(3)
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
        fake = [item_hash(proof[0]), proof[1]]  # root shown, both children hidden
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
        r = self.rec
        cases = {
            "record value changed": replaced(proof, (1, 0, 1), (11, "robot")),
            "left boundary removed": [[proof[0][0], proof[0][1], [self.h[7], r(9)]], proof[1]],
            "right boundary removed": [proof[0], [proof[1][0], [self.h[14], self.h[15], self.h[16]]]],
            "unknown item": replaced(proof, (0, 0), 12345),
            "record with 3 parts": replaced(proof, (1, 0, 0), (10, "teddy", "x")),
            "hash too short": replaced(proof, (0, 0), self.L[1][:31]),
            "root not a list": self.root,
            "no proof": None,
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


if __name__ == "__main__":
    unittest.main()

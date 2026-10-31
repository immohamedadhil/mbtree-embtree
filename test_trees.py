"""Tests. Run with:  python -m unittest -v test_trees"""
import itertools
import random
import unittest
from unittest.mock import patch

from bptree import BPlusTree
from hashing import H, encode_record, node_hash, record_hash
from mbtree import MBTree

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


if __name__ == "__main__":
    unittest.main()

"""Tests. Run with:  python -m unittest -v test_trees"""
import itertools
import random
import unittest

from bptree import BPlusTree

# The 16-key toy example (email): key -> toy name.
TOY16 = {
    1: "ball", 2: "car", 3: "doll", 4: "kite",
    5: "yo-yo", 6: "puzzle", 7: "drum", 8: "train",
    9: "blocks", 10: "teddy", 11: "top", 12: "whistle",
    13: "marbles", 14: "jump rope", 15: "rattle", 16: "bubbles",
}


class TestBPlusTree(unittest.TestCase):

    def build(self, items, fanout=4):
        """Insert items one by one, checking every B+ rule after each insert."""
        tree = BPlusTree(fanout)
        for k, v in items:
            tree.insert(k, v)
            tree.check_invariants()
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
            tree.check_invariants()
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
                tree.check_invariants()

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
        tree.check_invariants()

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
            BPlusTree(fanout=2)                      # A6: fanout must be at least 3
        for bad in ("5", 1.5, True):                 # A8: search/range also need int keys
            with self.assertRaises(TypeError):
                tree.search(bad)
            with self.assertRaises(TypeError):
                tree.range_search(bad, 10)
            with self.assertRaises(TypeError):
                tree.range_search(1, bad)
            with self.assertRaises(TypeError):
                BPlusTree().search(bad)              # same error on an empty tree

    def test_empty_tree(self):
        tree = BPlusTree()
        tree.check_invariants()
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


if __name__ == "__main__":
    unittest.main()

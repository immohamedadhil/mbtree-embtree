"""Embedded Merkle B-tree (EMB-tree), paper Section 3.3.

The same B+ tree (external fanout f_e = `fanout`), but inside every node there
is a small Merkle tree with fanout f_k (`fk`) built over the node's entry
hashes. The root of that small tree is the node's hash, used by its parent.

Shape of the small tree (assumption A1; the paper assumes full nodes and leaves
the general case open): take the entry hashes f_k at a time from the left, hash
each group (even a group of one), and repeat until one hash is left.
For f_k >= f_e there is a single group, so every node hash equals the MB-tree's
(paper: "the authentication cost becomes equal to that of an MB-tree").

The small tree is stored in the node (`levels`).
- update: only the changed entry's path through each small tree on the way to
  the root is recomputed (paper Section 4.3).
- insert: the small trees of the changed nodes are rebuilt, because a new entry
  shifts the later entries into different groups (and a node may split).

Proofs use the same formats as the MB-tree, so verify.py checks both trees.
"""
from bisect import bisect_right

from bptree import BPlusTree, Inner, Leaf
from hashing import node_hash, record_hash


def build_levels(entry_hashes, fk):
    """A node's small tree: levels[0] = the entry hashes, levels[-1] = [the node's hash]."""
    levels = [list(entry_hashes)]
    while len(levels) == 1 or len(levels[-1]) > 1:
        below = levels[-1]
        groups = [node_hash(below[i:i + fk]) for i in range(0, len(below), fk)]
        levels.append(groups or [node_hash([])])  # an empty tree: same root as the MB-tree
    return levels


class EMBLeaf(Leaf):
    __slots__ = ("levels",)

    def __init__(self, keys, values):
        super().__init__(keys, values)
        self.levels = [[]]  # levels[0][i] = H(record i); the levels above are the small tree

    @property
    def digest(self):
        return self.levels[-1][0]


class EMBInner(Inner):
    __slots__ = ("levels",)

    def __init__(self, keys, children):
        super().__init__(keys, children)
        self.levels = [[]]  # levels[0][i] = hash of child i; the levels above are the small tree

    @property
    def digest(self):
        return self.levels[-1][0]


class EMBTree(BPlusTree):
    leaf_class = EMBLeaf
    inner_class = EMBInner

    def __init__(self, fanout=4, fk=2):
        if fk < 2:
            raise ValueError("fk must be at least 2")
        super().__init__(fanout)
        self.fk = fk
        self.root.levels = build_levels([], fk)

    @property
    def root_hash(self):
        return self.root.digest

    # ---------- authenticated read (the server's side) ----------

    def read(self, key):
        """Return (value, proof).

        Same proof format as the MB-tree: [(left_hashes, right_hashes), ...],
        bottom-up. Here every node adds one step per level of its small tree,
        each with at most f_k - 1 hashes (paper: (f_k - 1) * d_k per node).
        Key missing (assumption A4): (None, the range proof for [key, key]),
        which proves the key is absent.
        """
        path, leaf, i = self._locate(key)
        if i is None:
            return None, self.read_range(key, key)[1]
        proof = self._steps_in_node(leaf, i)
        for node, j in reversed(path):  # leaf's parent first, root last
            proof += self._steps_in_node(node, j)
        return leaf.values[i], proof

    def _steps_in_node(self, node, i):
        """The path from entry i up through the node's small tree."""
        steps = []
        for level in node.levels[:-1]:
            start = i - i % self.fk  # first member of i's group
            group = level[start:start + self.fk]
            steps.append((group[:i - start], group[i - start + 1:]))
            i //= self.fk  # the group's position one level up
        return steps

    def read_range(self, low, high):
        """Return (records, proof) for all records with low <= key <= high.

        Same proof format as the MB-tree (nested lists of hashes, records and
        shown children). Inside each shown node, the small tree is shown the
        same way: groups holding no shown entry are replaced by their hash.
        """
        records, first, last = self._range_span(low, high)
        return records, self._range_proof(self.root, first, last)

    def _range_proof(self, node, first, last):
        if isinstance(node, Leaf):
            shown = [i for i, k in enumerate(node.keys) if first <= k <= last]
            lo, hi = (shown[0], shown[-1]) if shown else (0, -1)
            return self._small_tree_proof(node, lo, hi, lambda i: (node.keys[i], node.values[i]))
        lo = bisect_right(node.keys, first)  # the two walks pass through children lo..hi
        hi = bisect_right(node.keys, last)
        return self._small_tree_proof(
            node, lo, hi, lambda i: self._range_proof(node.children[i], first, last))

    def _small_tree_proof(self, node, lo, hi, shown_item):
        """The node's small tree, with entries lo..hi shown (as shown_item(i)) and
        every group that holds none of them replaced by its hash."""
        fk = self.fk
        levels = node.levels

        def group(d, g):
            # Group g on level d is made of positions g*fk ... on level d-1; each
            # of those positions covers `span` entries of the node.
            span = fk ** (d - 1)
            members = []
            for p in range(g * fk, min(g * fk + fk, len(levels[d - 1]))):
                if p * span > hi or (p + 1) * span <= lo:
                    members.append(levels[d - 1][p])  # no shown entry below: just its hash
                elif d == 1:
                    members.append(shown_item(p))
                else:
                    members.append(group(d - 1, p))
            return members

        return group(len(levels) - 1, 0)

    # ---------- keeping the hashes up to date ----------

    def _put_record(self, leaf, i, key, value):
        super()._put_record(leaf, i, key, value)
        leaf.levels[0].insert(i, record_hash(key, value))  # the only record hashed on insert

    def _split_leaf(self, leaf):
        signpost, right = super()._split_leaf(leaf)
        keep = len(leaf.keys)  # the record hashes move with their records
        right.levels = [leaf.levels[0][keep:]]
        del leaf.levels[0][keep:]
        return signpost, right

    def _after_insert(self, changed):
        for node in changed:  # bottom-up, so children are ready before their parent
            if isinstance(node, Leaf):
                entries = node.levels[0]
            else:
                entries = [child.digest for child in node.children]
            node.levels = build_levels(entries, self.fk)

    def _after_update(self, path, leaf, i):
        self._set_entry(leaf, i, record_hash(leaf.keys[i], leaf.values[i]))
        child = leaf
        for node, j in reversed(path):  # leaf's parent first, root last
            self._set_entry(node, j, child.digest)
            child = node

    def _set_entry(self, node, i, h):
        """Give entry i a new hash; recompute only its path up the node's small tree."""
        levels = node.levels
        levels[0][i] = h
        for d in range(1, len(levels)):
            i //= self.fk
            start = i * self.fk
            levels[d][i] = node_hash(levels[d - 1][start:start + self.fk])

    # ---------- checking (used by tests) ----------

    def check_hashes(self):
        """Recompute every small tree from the records alone; raise AssertionError if any stored hash differs."""
        def expected(node):
            if isinstance(node, Leaf):
                entries = [record_hash(k, v) for k, v in zip(node.keys, node.values)]
            else:
                entries = [expected(child) for child in node.children]
            levels = build_levels(entries, self.fk)
            assert node.levels == levels, "stale hash in a node's small tree"
            return levels[-1][0]

        expected(self.root)

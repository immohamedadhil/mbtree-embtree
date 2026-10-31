"""Merkle B-tree (MB-tree), paper Section 3.2.

A B+ tree whose entries carry hashes:
- leaf entry i:   h_i = H(record i)
- inner entry i:  h_i = the hash of child i = H(child's h_1 | ... | h_f)
The root's hash covers every record. The owner gives it to clients as the
trusted root; proofs (Step 3) are checked against it.

Storage note: the paper keeps each child's hash in the parent's entry (k|p|h).
Here every node keeps its own hash in `digest`, and the parent reads it through
its pointer. It is the same value, stored in one place.

Updates (paper Section 4.2): only the nodes on the path from the changed leaf
up to the root are re-hashed.
"""
from bptree import BPlusTree, Inner, Leaf
from hashing import node_hash, record_hash


class MBLeaf(Leaf):
    __slots__ = ("hashes", "digest")

    def __init__(self, keys, values):
        super().__init__(keys, values)
        self.hashes = []    # hashes[i] = H(record i)
        self.digest = None  # this node's hash = H(hashes[0] | hashes[1] | ...)


class MBInner(Inner):
    __slots__ = ("digest",)

    def __init__(self, keys, children):
        super().__init__(keys, children)
        self.digest = None  # H(children[0].digest | children[1].digest | ...)


def entry_hashes(node):
    """The h_i values of a node's entries."""
    if isinstance(node, Leaf):
        return node.hashes
    return [child.digest for child in node.children]


class MBTree(BPlusTree):
    leaf_class = MBLeaf
    inner_class = MBInner

    def __init__(self, fanout=4):
        super().__init__(fanout)
        self.root.digest = node_hash([])  # the hash of an empty tree

    @property
    def root_hash(self):
        return self.root.digest

    # ---------- keeping the hashes up to date ----------

    def _put_record(self, leaf, i, key, value):
        super()._put_record(leaf, i, key, value)
        leaf.hashes.insert(i, record_hash(key, value))  # the only record hashed on insert

    def _split_leaf(self, leaf):
        signpost, right = super()._split_leaf(leaf)
        keep = len(leaf.keys)  # the record hashes move with their records
        right.hashes = leaf.hashes[keep:]
        del leaf.hashes[keep:]
        return signpost, right

    def _after_insert(self, changed):
        for node in changed:  # bottom-up, so children are ready before their parent
            node.digest = node_hash(entry_hashes(node))

    def _after_update(self, path, leaf, i):
        leaf.hashes[i] = record_hash(leaf.keys[i], leaf.values[i])
        leaf.digest = node_hash(leaf.hashes)
        for node, _ in reversed(path):  # leaf's parent first, root last
            node.digest = node_hash(entry_hashes(node))

    # ---------- checking (used by tests) ----------

    def check_hashes(self):
        """Recompute every hash from the records alone; raise AssertionError if any stored hash differs."""
        def expected(node):
            if isinstance(node, Leaf):
                hashes = [record_hash(k, v) for k, v in zip(node.keys, node.values)]
                assert node.hashes == hashes, "stale record hash in a leaf"
            else:
                hashes = [expected(child) for child in node.children]
            digest = node_hash(hashes)
            assert node.digest == digest, "stale node hash"
            return digest

        expected(self.root)

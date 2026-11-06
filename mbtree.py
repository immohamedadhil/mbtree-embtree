"""Merkle B-tree (MB-tree), paper Section 3.2: a B+ tree whose nodes carry hashes.

B+ tree rules (README: "standard B+-tree search, insertion, and split behavior"):
Node sizes follow Silberschatz, Korth and Sudarshan, Database System Concepts
(7th ed., Section 14.3), with n = fanout f (at least 3):
- an inner node has at most f children (f - 1 signposts) and, except the
  root, at least ceil(f/2) children; the root has at least 2;
- a leaf holds at most f - 1 records (the book's last pointer, the link to
  the next leaf, is `next` here) and, except the root, at least ceil((f-1)/2).
- Leaf split: a leaf that already holds f - 1 records gets one more; the f
  records split into the first ceil(f/2) and the rest (f = 4: 4 -> 2 + 2).
  The first key of the new right leaf is COPIED up to the parent.
- Inner split: a node that already has f children gets one more; the first
  ceil((f+1)/2) children stay and the rest move (f = 4: 5 -> 3 + 2). The key
  between them is MOVED up to the parent (book Figure 14.17).
- When the root splits, a new root is made and the tree gets one level taller.
- Leaves are linked left to right, so a range search can walk along them.
- Keys are unique integers and values are text.

Hashes (paper Section 3.2):
- leaf entry i:   h_i = H(record i)
- inner entry i:  h_i = the hash of child i = H(child's h_1 | ... | h_f)
The root's hash covers every record. The owner gives it to clients as the
trusted root; proofs are checked against it (verify.py).

Storage note: the paper keeps each child's hash in the parent's entry (k|p|h).
Here every node keeps its own hash in `digest`, and the parent reads it through
its pointer. It is the same value, stored in one place.

Insert and update (paper Section 4.2): only the nodes on the path from the
changed leaf up to the root are re-hashed (and the new nodes of a split).
"""
from bisect import bisect_left, bisect_right

from hashing import node_hash, record_hash


class Leaf:
    """Up to `fanout` - 1 records, sorted by key, plus a link to the next leaf."""

    def __init__(self, keys, values, hashes):
        self.keys = keys
        self.values = values
        self.hashes = hashes     # hashes[i] = H(record i)
        self.next = None
        self.digest = None       # this node's hash
        self.small_tree = None   # EMB-tree only (embtree.py)


class Inner:
    """Up to `fanout` children and one signpost key between each pair.

    keys[i] is the smallest key in the subtree of children[i + 1].
    """

    def __init__(self, keys, children):
        self.keys = keys
        self.children = children
        self.digest = None       # this node's hash
        self.small_tree = None   # EMB-tree only (embtree.py)


def entry_hashes(node):
    """The h_i values of a node's entries."""
    if isinstance(node, Leaf):
        return node.hashes
    return [child.digest for child in node.children]


def _check_key(key):
    if not isinstance(key, int) or isinstance(key, bool):
        raise TypeError(f"key must be an int, got {type(key).__name__}")


def _check_types(key, value):
    _check_key(key)
    if not isinstance(value, str):
        raise TypeError(f"value must be a str, got {type(value).__name__}")


class MBTree:

    def __init__(self, fanout=4):
        if fanout < 3:
            raise ValueError("fanout must be at least 3")
        self.fanout = fanout
        self.root = Leaf([], [], [])
        self.height = 1  # number of levels; a tree with only a leaf has height 1
        self.size = 0    # number of records
        self._rehash(self.root)
        self.root_hash = self.root.digest  # the hash of an empty tree

    # ---------- search ----------

    def _descend(self, key):
        """Walk from the root to the leaf where `key` belongs.

        Returns (path, leaf), where path is a list of (inner_node, child_index)
        pairs from the root down: the steps taken to reach the leaf.
        """
        path = []
        node = self.root
        while isinstance(node, Inner):
            i = bisect_right(node.keys, key)  # keys equal to a signpost go right
            path.append((node, i))
            node = node.children[i]
        return path, node

    def _locate(self, key):
        """Find `key`. Returns (path, leaf, i) with leaf.keys[i] == key, or i = None if absent."""
        _check_key(key)
        path, leaf = self._descend(key)
        i = bisect_left(leaf.keys, key)
        if i < len(leaf.keys) and leaf.keys[i] == key:
            return path, leaf, i
        return path, leaf, None

    def search(self, key):
        """Return the value stored for `key`, or None if the key is not in the tree."""
        _, leaf, i = self._locate(key)
        if i is None:
            return None
        return leaf.values[i]

    def range_search(self, low, high):
        """Return [(key, value), ...] for every record with low <= key <= high, in key order."""
        _check_key(low)
        _check_key(high)
        _, leaf = self._descend(low)
        i = bisect_left(leaf.keys, low)
        result = []
        while leaf is not None:
            while i < len(leaf.keys):
                if leaf.keys[i] > high:
                    return result
                result.append((leaf.keys[i], leaf.values[i]))
                i += 1
            leaf = leaf.next
            i = 0
        return result

    def _key_before(self, key):
        """The largest key in the tree that is smaller than `key`, or None."""
        path, leaf = self._descend(key)
        i = bisect_left(leaf.keys, key)
        if i > 0:
            return leaf.keys[i - 1]
        # Everything in this leaf is >= key: go up until I can step one child
        # to the left, then down that subtree's right edge to its last key.
        for node, j in reversed(path):
            if j > 0:
                child = node.children[j - 1]
                while isinstance(child, Inner):
                    child = child.children[-1]
                return child.keys[-1]
        return None

    def _key_after(self, key):
        """The smallest key in the tree that is larger than `key`, or None."""
        _, leaf = self._descend(key)
        i = bisect_right(leaf.keys, key)
        if i < len(leaf.keys):
            return leaf.keys[i]
        if leaf.next is not None:
            return leaf.next.keys[0]
        return None

    def _range_span(self, low, high):
        """What a range proof must show: (records, first, last).

        records: every record with low <= key <= high.
        first..last: the keys to show = the records plus one boundary record on
        each side (paper Section 3.2): the largest key < low and the smallest
        key > high. Both are None for an empty tree.
        """
        records = self.range_search(low, high)
        before = self._key_before(low)
        after = self._key_after(high)
        first = before
        if first is None:
            first = records[0][0] if records else after
        last = after
        if last is None:
            last = records[-1][0] if records else before
        if first is not None and first > last:
            # Only when low > high and some keys lie between them: showing one of
            # those keys (it is > high and < low) proves the empty answer.
            first = last = after
        return records, first, last

    # ---------- insert ----------

    def insert(self, key, value):
        """Insert a new record and return a non-membership proof: the proof that
        `key` was not in the tree before, checked against the root from before
        this insert (verify_read(key, None, proof, old_root)).
        Raises KeyError if the key exists: then no such proof is possible."""
        _check_types(key, value)
        found, proof = self.read(key)
        if found is not None:
            raise KeyError(f"key {key} already exists")

        h = record_hash(key, value)  # the only record hashed on insert (before any change)
        path, leaf = self._descend(key)
        i = bisect_left(leaf.keys, key)
        leaf.keys.insert(i, key)
        leaf.values.insert(i, value)
        leaf.hashes.insert(i, h)
        self.size += 1

        changed = [leaf]  # every node whose contents changed, bottom-up
        node = leaf
        while self._overfull(node):
            # Too full: split it and add the new right half to the parent.
            if isinstance(node, Leaf):
                signpost, right = self._split_leaf(node)
            else:
                signpost, right = self._split_inner(node)
            changed.append(right)
            if path:
                parent, j = path.pop()
                parent.keys.insert(j, signpost)
                parent.children.insert(j + 1, right)
            else:
                # The root itself split: make a new root above the two halves.
                parent = Inner([signpost], [node, right])
                self.root = parent
                self.height += 1
            changed.append(parent)
            node = parent

        # Nodes further up keep their shape, but something below them changed.
        for node, _ in reversed(path):
            changed.append(node)
        for node in changed:  # bottom-up, so children are ready before their parent
            self._rehash(node)
        self.root_hash = self.root.digest
        return proof

    def _overfull(self, node):
        if isinstance(node, Leaf):
            return len(node.keys) > self.fanout - 1  # a leaf holds at most f - 1 records
        return len(node.children) > self.fanout

    def _split_leaf(self, leaf):
        """Split an over-full leaf. Returns (signpost copied up, new right leaf)."""
        keep = (len(leaf.keys) + 1) // 2  # the left half gets the extra record
        right = Leaf(leaf.keys[keep:], leaf.values[keep:], leaf.hashes[keep:])
        del leaf.keys[keep:]
        del leaf.values[keep:]
        del leaf.hashes[keep:]  # the record hashes move with their records
        right.next = leaf.next
        leaf.next = right
        return right.keys[0], right

    def _split_inner(self, node):
        """Split an over-full inner node. Returns (signpost moved up, new right node)."""
        keep = (len(node.children) + 1) // 2  # the left half gets the extra child
        signpost = node.keys[keep - 1]
        right = Inner(node.keys[keep:], node.children[keep:])
        del node.keys[keep - 1:]
        del node.children[keep:]
        return signpost, right

    # ---------- update ----------

    def update(self, key, new_value):
        """Change the value of an existing record. Raises KeyError if the key is missing."""
        _check_types(key, new_value)
        path, leaf, i = self._locate(key)
        if i is None:
            raise KeyError(f"key {key} not found")
        h = record_hash(key, new_value)  # before any change
        leaf.values[i] = new_value
        leaf.hashes[i] = h
        self._update_hashes(path, leaf, i)
        self.root_hash = self.root.digest

    # ---------- authenticated reads (the server's side) ----------

    def read(self, key):
        """Return (value, proof).

        Key found: the proof lists, for every node from the leaf up to the root,
        the hashes to the LEFT and to the RIGHT of the entry on the path:
            [(left_hashes, right_hashes), ...]   (leaf first, root last)
        The client hashes the record, puts it between left and right, hashes
        that node, and repeats up to the root (see verify.py).

        Key missing (assumption A4): value is None and the proof is the range
        proof for [key, key]. It shows the two neighbouring records, so it
        proves the key is absent; a server cannot hide a record by just
        saying "not found".
        """
        path, leaf, i = self._locate(key)
        if i is None:
            records, proof = self.read_range(key, key)
            return None, proof
        proof = self._steps_in_node(leaf, i)
        for node, j in reversed(path):  # leaf's parent first, root last
            proof += self._steps_in_node(node, j)
        return leaf.values[i], proof

    def read_range(self, low, high):
        """Return (records, proof) for all records with low <= key <= high.

        Paper Section 3.2, Figure 4: the proof also carries one boundary record
        on each side (the largest key < low and the smallest key > high), so the
        client can check that nothing in the range was left out.

        The proof is a copy of the tree in which every part the client does not
        need is replaced by its hash. Each node is a list of items:
            bytes           the hash of a hidden record or hidden subtree
            (key, value)    a record that is shown
            list            a child node that is shown (same format, nested)
        The nesting is the paper's "node boundary information" (footnote 1).
        """
        records, first, last = self._range_span(low, high)
        return records, self._range_proof(self.root, first, last)

    def _range_proof(self, node, first, last):
        """One node of a range proof. Entries lo..hi are shown: in a leaf the records
        with first <= key <= last, in an inner node the children that the walks to
        `first` and `last` pass through. Every other entry is replaced by its hash."""
        shown = []
        if isinstance(node, Leaf):
            lo = bisect_left(node.keys, first)
            hi = bisect_right(node.keys, last) - 1
            for i in range(lo, hi + 1):
                shown.append((node.keys[i], node.values[i]))
        else:
            lo = bisect_right(node.keys, first)
            hi = bisect_right(node.keys, last)
            for i in range(lo, hi + 1):
                shown.append(self._range_proof(node.children[i], first, last))
        return self._show_in_node(node, lo, hi, shown)

    # ---------- one node: how it is hashed and shown (the EMB-tree changes these) ----------

    def _rehash(self, node):
        """Recompute the node's hash from its entries."""
        node.digest = node_hash(entry_hashes(node))

    def _update_hashes(self, path, leaf, i):
        """After record i of `leaf` changed: re-hash the leaf and every node above it."""
        self._rehash(leaf)
        for node, _ in reversed(path):  # leaf's parent first, root last
            self._rehash(node)

    def _steps_in_node(self, node, i):
        """Read-proof steps for entry i of a node: the hashes left and right of it."""
        hashes = entry_hashes(node)
        return [(hashes[:i], hashes[i + 1:])]

    def _show_in_node(self, node, lo, hi, shown):
        """The node as a range-proof list: the hashes left of the shown entries,
        the shown entries (lo..hi), then the hashes right of them."""
        hashes = entry_hashes(node)
        return hashes[:lo] + shown + hashes[hi + 1:]

    # ---------- inspection (used by tests and the demo) ----------

    def levels(self):
        """The keys of every node, level by level: [[root keys], [next level...], ...]."""
        out = []
        nodes = [self.root]
        while nodes:
            out.append([list(n.keys) for n in nodes])
            below = []
            for n in nodes:
                if isinstance(n, Inner):
                    below += n.children
            nodes = below
        return out

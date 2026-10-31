"""Plain in-memory B+ tree (no hashing yet).

This is the shared skeleton for the MB-tree and the EMB-tree: sorted keys,
search, range search, insert with node splits, and value update.

Rules used (README: "standard B+-tree search, insertion, and split behavior"):
- fanout f = the maximum number of entries in a node
  (records in a leaf, children in an inner node); f must be at least 3.
- A node that gets f + 1 entries splits into two halves; when the count is
  odd, the LEFT half gets the extra entry (f = 4: 5 -> 3 + 2).
- Leaf split: the first key of the right half is COPIED up to the parent.
- Inner split: the middle key is MOVED up to the parent.
- When the root splits, a new root is made and the tree gets one level taller.
- Leaves are linked left to right, so a range search can walk along them.
- Keys are unique integers and values are text.
"""
from bisect import bisect_left, bisect_right


class Leaf:
    """Up to `fanout` records, sorted by key, plus a link to the next leaf."""
    __slots__ = ("keys", "values", "next")

    def __init__(self, keys, values):
        self.keys = keys
        self.values = values
        self.next = None


class Inner:
    """Up to `fanout` children and one signpost key between each pair.

    keys[i] is the smallest key in the subtree of children[i + 1].
    """
    __slots__ = ("keys", "children")

    def __init__(self, keys, children):
        self.keys = keys
        self.children = children


def _check_key(key):
    if not isinstance(key, int) or isinstance(key, bool):
        raise TypeError(f"key must be an int, got {type(key).__name__}")


def _check_types(key, value):
    _check_key(key)
    if not isinstance(value, str):
        raise TypeError(f"value must be a str, got {type(value).__name__}")


class BPlusTree:
    # The MB-tree and EMB-tree swap in node classes that also store hashes,
    # and override the "hooks" at the bottom of this class.
    leaf_class = Leaf
    inner_class = Inner

    def __init__(self, fanout=4):
        if fanout < 3:
            raise ValueError("fanout must be at least 3")
        self.fanout = fanout
        self.root = self.leaf_class([], [])
        self.height = 1  # number of levels; a tree with only a leaf has height 1
        self.size = 0    # number of records

    def __len__(self):
        return self.size

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
        return None if i is None else leaf.values[i]

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
        # Everything in this leaf is >= key: go up until we can step one child
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
        first = before if before is not None else (records[0][0] if records else after)
        last = after if after is not None else (records[-1][0] if records else before)
        if first is not None and first > last:
            # Only when low > high and some keys lie between them: showing one of
            # those keys (it is > high and < low) proves the empty answer.
            first = last = after
        return records, first, last

    # ---------- insert ----------

    def insert(self, key, value):
        """Add a new record. Raises KeyError if the key already exists."""
        _check_types(key, value)
        path, leaf = self._descend(key)
        i = bisect_left(leaf.keys, key)
        if i < len(leaf.keys) and leaf.keys[i] == key:
            raise KeyError(f"key {key} already exists")
        self._put_record(leaf, i, key, value)
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
                parent, i = path.pop()
                parent.keys.insert(i, signpost)
                parent.children.insert(i + 1, right)
            else:
                # The root itself split: make a new root above the two halves.
                parent = self.inner_class([signpost], [node, right])
                self.root = parent
                self.height += 1
            changed.append(parent)
            node = parent

        # Nodes further up keep their shape, but something below them changed.
        changed.extend(n for n, _ in reversed(path))
        self._after_insert(changed)

    def _overfull(self, node):
        if isinstance(node, Leaf):
            return len(node.keys) > self.fanout
        return len(node.children) > self.fanout

    def _split_leaf(self, leaf):
        """Split an over-full leaf. Returns (signpost copied up, new right leaf)."""
        keep = (len(leaf.keys) + 1) // 2  # the left half gets the extra record
        right = self.leaf_class(leaf.keys[keep:], leaf.values[keep:])
        del leaf.keys[keep:]
        del leaf.values[keep:]
        right.next = leaf.next
        leaf.next = right
        return right.keys[0], right

    def _split_inner(self, node):
        """Split an over-full inner node. Returns (signpost moved up, new right node)."""
        keep = (len(node.children) + 1) // 2  # the left half gets the extra child
        signpost = node.keys[keep - 1]
        right = self.inner_class(node.keys[keep:], node.children[keep:])
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
        leaf.values[i] = new_value
        self._after_update(path, leaf, i)

    # ---------- hooks: do nothing here; the MB-tree and EMB-tree fill them in ----------

    def _put_record(self, leaf, i, key, value):
        """Place a new record at position i of a leaf."""
        leaf.keys.insert(i, key)
        leaf.values.insert(i, value)

    def _after_insert(self, changed):
        """Called after an insert, with every changed node listed bottom-up."""

    def _after_update(self, path, leaf, i):
        """Called after update() changed the value at position i of `leaf`."""

    # ---------- inspection (used by tests and the demo) ----------

    def levels(self):
        """The keys of every node, level by level: [[root keys], [next level...], ...]."""
        out = []
        nodes = [self.root]
        while nodes:
            out.append([list(n.keys) for n in nodes])
            nodes = [c for n in nodes if isinstance(n, Inner) for c in n.children]
        return out

    def __str__(self):
        return "\n".join(" ".join(str(keys) for keys in level) for level in self.levels())

    def check_invariants(self):
        """Raise AssertionError if any B+ tree rule is broken."""
        min_fill = (self.fanout + 1) // 2  # "at least half full" for non-root nodes
        leaves = []

        def walk(node, depth, is_root):
            """Check `node`'s subtree; return its (smallest key, largest key)."""
            assert node.keys == sorted(node.keys), "keys not sorted"
            assert len(set(node.keys)) == len(node.keys), "duplicate keys in a node"
            if isinstance(node, Leaf):
                assert len(node.keys) == len(node.values), "keys/values length mismatch"
                assert len(node.keys) <= self.fanout, "leaf over-full"
                if not is_root:
                    assert len(node.keys) >= min_fill, "leaf under-full"
                assert depth == self.height, "leaves not all at the same depth"
                leaves.append(node)
                return node.keys[0], node.keys[-1]
            n = len(node.children)
            assert len(node.keys) == n - 1, "inner node needs one fewer key than children"
            assert n <= self.fanout, "inner node over-full"
            assert n >= (2 if is_root else min_fill), "inner node under-full"
            lo, hi = walk(node.children[0], depth + 1, False)
            smallest = lo
            for i, signpost in enumerate(node.keys):
                assert hi < signpost, "a key on the left is not smaller than its signpost"
                lo, hi = walk(node.children[i + 1], depth + 1, False)
                assert lo == signpost, "signpost is not the smallest key on its right"
            return smallest, hi

        if self.size == 0:
            assert isinstance(self.root, Leaf) and not self.root.keys, "empty tree must be one empty leaf"
            return
        walk(self.root, 1, True)

        # The leaf links must visit exactly the leaves above, in the same order.
        assert leaves[-1].next is None, "last leaf must not link anywhere"
        for a, b in zip(leaves, leaves[1:]):
            assert a.next is b, "leaf links are broken"
        assert sum(len(leaf.keys) for leaf in leaves) == self.size, "size counter is wrong"

"""Embedded Merkle B-tree (EMB-tree), paper Section 3.3.

The same B+ tree as the MB-tree (external fanout f_e = `fanout`), but inside
every node there is a small Merkle tree with fanout f_k (`fk`) built over the
node's entry hashes. The root of that small tree is the node's hash, used by
its parent. So the EMB-tree is the MB-tree with four changes, all about one
node: how it is hashed, how it is updated, and how it is shown in a read proof
and in a range proof. Everything else (search, insert, splits) is shared.

Nodes that are not full: the paper assumes full nodes. As suggested by the task
reviewer, the empty places are filled with a fixed value, EMPTY = 32 zero bytes.
Each node's small tree has `slots` places (the smallest power of f_k that holds
f_e entries), so every group is full and every small tree has the same shape:
d_k = log_fk(slots) levels and exactly f_k - 1 hashes per level in a proof, as
in the paper's cost model. A group made only of EMPTY slots is itself EMPTY.
For f_k >= f_e there is no small tree (the paper discards it): the node is
hashed exactly like an MB-tree node.

The small tree is stored in the node (`small_tree`, a list of levels).
- update: only the changed entry's path through each small tree on the way to
  the root is recomputed (paper Section 4.3).
- insert: the small trees of the changed nodes are rebuilt, because a new entry
  shifts the later entries into different groups (and a node may split).

Proofs use the same formats as the MB-tree, so verify.py checks both trees.
"""
from hashing import EMPTY, node_hash
from mbtree import MBTree, entry_hashes


def slots_for(fanout, fk):
    """Places in a node's small tree: the smallest power of fk that holds `fanout`
    entries, or None when fk >= fanout (no small tree)."""
    if fk >= fanout:
        return None
    slots = fk
    while slots < fanout:
        slots *= fk
    return slots


def group_hash(members):
    """A group of only EMPTY slots stays EMPTY; any other group is hashed as a node."""
    if all(m == EMPTY for m in members):
        return EMPTY
    return node_hash(members)


def build_small_tree(entry_hashes, fk, slots):
    """A node's small tree, as a list of levels: the first level is the entry
    hashes padded with EMPTY up to `slots`; the last level is [the node's hash]."""
    entries = list(entry_hashes)
    if slots is None:  # fk >= fanout: one group, exactly the MB-tree's node hash
        return [entries, [node_hash(entries)]]
    assert len(entries) <= slots, "more entries than slots"
    levels = [entries + [EMPTY] * (slots - len(entries))]
    while len(levels[-1]) > 1:
        below = levels[-1]
        above = []
        for start in range(0, len(below), fk):
            above.append(group_hash(below[start:start + fk]))
        levels.append(above)
    return levels


class EMBTree(MBTree):

    def __init__(self, fanout=4, fk=2):
        if fk < 2:
            raise ValueError("fk must be at least 2")
        # set before MBTree.__init__, which already hashes the (empty) root
        self.fk = fk
        self.slots = slots_for(fanout, fk)
        super().__init__(fanout)

    # ---------- the four changes ----------

    def _rehash(self, node):
        """Rebuild the node's small tree from its entries; its top is the node's hash."""
        node.small_tree = build_small_tree(entry_hashes(node), self.fk, self.slots)
        node.digest = node.small_tree[-1][0]

    def _update_hashes(self, path, leaf, i):
        """Paper Section 4.3: after record i of `leaf` changed, recompute only the
        path up each small tree, from the leaf to the root."""
        self._set_entry(leaf, i, leaf.hashes[i])
        child = leaf
        for node, j in reversed(path):  # leaf's parent first, root last
            self._set_entry(node, j, child.digest)
            child = node

    def _steps_in_node(self, node, i):
        """Read-proof steps for entry i: one step per level of the small tree, each
        with the other members of i's group (f_k - 1 hashes; paper: (f_k - 1) * d_k)."""
        steps = []
        for level in node.small_tree[:-1]:
            start = i - i % self.fk  # first member of i's group
            group = level[start:start + self.fk]
            steps.append((group[:i - start], group[i - start + 1:]))
            i = i // self.fk  # the group's position one level up
        return steps

    def _show_in_node(self, node, lo, hi, shown):
        """The node's small tree as a range-proof list, with entries lo..hi shown.
        Going up one level at a time, every group that holds a shown entry is
        opened (a list of its members); every other group stays a hash (EMPTY for
        a group of only empty slots)."""
        fk = self.fk
        levels = node.small_tree
        for level in levels[:-2]:  # every level below the top group
            group_lo, group_hi = lo // fk, hi // fk  # the groups that get opened
            # their members, in order: hashes, the shown part, hashes
            members = level[group_lo * fk:lo] + shown + level[hi + 1:(group_hi + 1) * fk]
            shown = []
            for start in range(0, len(members), fk):
                shown.append(members[start:start + fk])
            lo, hi = group_lo, group_hi
        top_group = levels[-2]
        return top_group[:lo] + shown + top_group[hi + 1:]

    # ---------- helper ----------

    def _set_entry(self, node, i, h):
        """Give entry i a new hash; recompute only its path up the node's small tree."""
        levels = node.small_tree
        levels[0][i] = h
        for d in range(1, len(levels)):
            i = i // self.fk
            start = i * self.fk
            levels[d][i] = group_hash(levels[d - 1][start:start + self.fk])
        node.digest = levels[-1][0]

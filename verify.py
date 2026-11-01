"""Client-side proof checking.

The client never sees the tree. It only has:
- the answer the server sent (key and value),
- the proof the server sent,
- the trusted root hash, which it got from the owner, not from the server (README).

Paper Section 2.1 / 3.2: the client recomputes the root from the answer and the
proof. If it equals the trusted root, the answer is genuine; changing the value
or the proof would need a SHA-256 collision.
"""
from hashing import HASH_SIZE, node_hash, record_hash


def _is_hash(h):
    return isinstance(h, bytes) and len(h) == HASH_SIZE


def root_from_path(h, steps):
    """Climb from hash h to the root.

    steps: [(left_hashes, right_hashes), ...], bottom step first.
    At each step the node's hash is H(0x01 | left | h | right).
    """
    for left, right in steps:
        h = node_hash(list(left) + [h] + list(right))
    return h


HIDDEN = None  # marks "a hash stands here for something not shown"


def _rebuild(node, seq):
    """Hash one node of a range proof (recursively).

    Also appends what the client "sees" at the bottom of the tree to `seq`, in
    key order: a (key, value) record, or HIDDEN for a hash that stands for
    something not shown.
    """
    if not isinstance(node, list):
        raise ValueError("a node must be a list")
    hashes = []
    for item in node:
        if isinstance(item, bytes):    # hidden record or hidden subtree
            if not _is_hash(item):
                raise ValueError("bad hash")
            hashes.append(item)
            seq.append(HIDDEN)
        elif isinstance(item, tuple):  # a record that is shown
            key, value = item
            hashes.append(record_hash(key, value))
            seq.append((key, value))
        elif isinstance(item, list):   # a child node that is shown
            hashes.append(_rebuild(item, seq))
        else:
            raise ValueError("unknown item in proof")
    return node_hash(hashes)


def verify_range(low, high, records, proof, trusted_root):
    """True if `records` is exactly every record with low <= key <= high in the
    tree whose root hash is trusted_root: correct AND complete."""
    try:
        seq = []
        if _rebuild(proof, seq) != trusted_root:
            return False  # 1. correctness: the shown records really are in the tree

        shown = [i for i, x in enumerate(seq) if x is not HIDDEN]
        if not shown:
            return seq == []  # no records shown at all is only fine for an empty tree
        # 2. the shown records sit next to each other: nothing hidden between them
        if shown != list(range(shown[0], shown[-1] + 1)):
            return False
        # (The records come out in key order: the owner built the tree sorted,
        # and the root hash fixes that order.)
        recs = [seq[i] for i in shown]
        # 3. left end: a boundary record below `low`, or nothing at all before it
        if not (recs[0][0] < low or shown[0] == 0):
            return False
        # 4. right end: a boundary record above `high`, or nothing at all after it
        if not (recs[-1][0] > high or shown[-1] == len(seq) - 1):
            return False
        # 5. the answer is exactly the shown records inside the range
        return [(k, v) for k, v in recs if low <= k <= high] == list(records)
    except (TypeError, ValueError, AttributeError, RecursionError):
        return False  # a proof of the wrong shape (or absurdly deep) is simply rejected


def verify_read(key, value, proof, trusted_root):
    """True if (key, value) is a record in the tree whose root hash is trusted_root.

    value None means "not found": then the proof must show that the key is
    absent (it is the range proof for [key, key]).
    """
    if value is None:
        return verify_range(key, key, [], proof, trusted_root)
    try:
        for left, right in proof:
            if not all(_is_hash(x) for x in list(left) + list(right)):
                return False  # malformed proof
        return root_from_path(record_hash(key, value), proof) == trusted_root
    except (TypeError, ValueError, AttributeError):
        return False  # a proof or answer of the wrong shape is simply rejected

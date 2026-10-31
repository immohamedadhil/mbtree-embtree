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


def verify_read(key, value, proof, trusted_root):
    """True if (key, value) is a record in the tree whose root hash is trusted_root."""
    try:
        for left, right in proof:
            if not all(_is_hash(x) for x in list(left) + list(right)):
                return False  # malformed proof
        return root_from_path(record_hash(key, value), proof) == trusted_root
    except (TypeError, ValueError, AttributeError):
        return False  # a proof or answer of the wrong shape is simply rejected

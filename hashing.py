"""SHA-256 hashing rules shared by the MB-tree and the EMB-tree.

Paper (Section 3.2):  leaf entry  h = H(r)            (r = the record)
                      index entry h = H(h_1|...|h_f)  (the child's entry hashes, joined)

Assumption A2 (not in the paper): a one-byte label goes in front of everything
we hash, as in RFC 6962 Section 2.1:  0x00 for a record, 0x01 for a node.
So a node hash can never be passed off as a record hash, or the other way round.
"""
import hashlib

HASH_SIZE = 32  # bytes in one SHA-256 hash
RECORD_TAG = b"\x00"
NODE_TAG = b"\x01"


def H(data):
    return hashlib.sha256(data).digest()


def encode_record(key, value):
    """Turn a record into bytes, the same way every time.

    key:   signed big-endian integer (any size, also negative), with its length in front
    value: UTF-8 text, with its length in front
    The lengths make the bytes unambiguous: two different records never give the
    same bytes (without them, (1, "23") and (12, "3") could collide).
    """
    k = key.to_bytes((key.bit_length() + 8) // 8, "big", signed=True)
    v = value.encode("utf-8")
    return len(k).to_bytes(4, "big") + k + len(v).to_bytes(4, "big") + v


def record_hash(key, value):
    """h = H(0x00 | record)"""
    return H(RECORD_TAG + encode_record(key, value))


def node_hash(entry_hashes):
    """h = H(0x01 | h_1 | h_2 | ... | h_n)"""
    return H(NODE_TAG + b"".join(entry_hashes))

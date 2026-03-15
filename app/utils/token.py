import hashlib


def hash_token(raw: str) -> str:
    """SHA-256 hash of a raw invite token for storage and lookup."""
    return hashlib.sha256(raw.encode()).hexdigest()

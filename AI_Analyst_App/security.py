import re

import base64
import hashlib

from cryptography.fernet import Fernet

from config import DATASET_ENCRYPTION_KEY, JWT_SECRET, SESSION_SECRET


def _fernet() -> Fernet:
    key = DATASET_ENCRYPTION_KEY.strip()
    if not key:
        # Dev fallback: derive a stable 32-byte key from other app secrets so
        # nothing crashes locally. Set DATASET_ENCRYPTION_KEY for real use.
        digest = hashlib.sha256(f"{JWT_SECRET}:{SESSION_SECRET}".encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypts a database password (or similar) for storage in Firestore."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


FORBIDDEN_KEYWORDS = [
    "drop",
    "delete",
    "update",
    "insert",
    "alter",
    "truncate",
    "grant",
    "revoke",
    "create",
    "replace"
]

def sanitize_sql(query: str) -> str:
    query = query.replace("```sql", "")
    query = query.replace("```", "")
    query = query.strip()
    return query

def is_read_only_query(query: str) -> bool:
    query = query.strip().lower()

    return (
        query.startswith("select")
        or query.startswith("with")
    )

def check_forbidden_keywords(query: str) -> None:
    query_lower = query.lower()

    for keyword in FORBIDDEN_KEYWORDS:
        pattern = rf"\b{keyword}\b"

        if re.search(pattern, query_lower):
            raise ValueError(
                f"Forbidden SQL keyword detected: {keyword}"
            )

def validate_sql(query: str) -> bool:
    query = sanitize_sql(query)

    if not is_read_only_query(query):
        raise ValueError(
            "Only SELECT and WITH queries are allowed."
        )

    check_forbidden_keywords(query)

    return True
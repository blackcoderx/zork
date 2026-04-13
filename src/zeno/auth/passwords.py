import bcrypt as _bcrypt


def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return _bcrypt.checkpw(plain.encode(), hashed.encode())

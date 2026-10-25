import pytest
from helpers import hash_password, check_password


def test_hash_password():
    """Test that hash_password produces a valid hash string."""
    password = "testpass123"
    hashed = hash_password(password)
    # Should contain a salt and hashed portion separated by $
    assert "$" in hashed
    salt, stored_hashed = hashed.split("$", 1)
    # Salt should be 16 hex characters (8 bytes hex)
    assert len(salt) == 16
    # Stored hashed should be 64 hex characters (SHA-256)
    assert len(stored_hashed) == 64


def test_check_password_correct():
    """Test that check_password verifies a correct password."""
    password = "testpass123"
    hashed = hash_password(password)
    assert check_password(password, hashed) is True


def test_check_password_incorrect():
    """Test that check_password rejects an incorrect password."""
    password = "testpass123"
    hashed = hash_password(password)
    assert check_password("wrongpass", hashed) is False


def test_check_password_different_users():
    """Test that passwords hashed separately are not interchangeable."""
    hashed1 = hash_password("secret")
    hashed2 = hash_password("secret")
    # Even with same password, salts should differ
    assert hashed1 != hashed2
    # But both should verify the same password
    assert check_password("secret", hashed1) is True
    assert check_password("secret", hashed2) is True
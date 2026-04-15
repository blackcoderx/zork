"""Tests for access/refresh token functions.

Covers:
- create_access_token() creates token with correct type claim
- create_refresh_token() creates token with correct type claim
- verify_token_type() validates token types correctly
- Token uniqueness (unique JTI for each token)
- Token expiry handling
"""

import pytest

from zork.auth.tokens import (
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    create_token,
    decode_token,
    verify_token_type,
)
from zork.errors import ZorkError


class TestAccessToken:
    SECRET = "test-secret-key-for-testing"

    def test_create_access_token_has_correct_type(self):
        token = create_access_token("user-123", "user", 3600, self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert payload["type"] == TOKEN_TYPE_ACCESS

    def test_access_token_has_required_claims(self):
        token = create_access_token("user-123", "user", 3600, self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert payload["sub"] == "user-123"
        assert payload["role"] == "user"
        assert "jti" in payload
        assert "exp" in payload
        assert "iat" in payload
        assert "type" in payload

    def test_access_token_expired_raises(self):
        token = create_access_token("user-123", "user", -1, self.SECRET)
        with pytest.raises(ZorkError) as exc_info:
            decode_token(token, self.SECRET)
        assert exc_info.value.status_code == 401

    def test_access_token_invalid_raises(self):
        with pytest.raises(ZorkError) as exc_info:
            decode_token("invalid.token.here", self.SECRET)
        assert exc_info.value.status_code == 401


class TestRefreshToken:
    SECRET = "test-secret-key-for-testing"

    def test_create_refresh_token_has_correct_type(self):
        token = create_refresh_token("user-456", "admin", 604800, self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert payload["type"] == TOKEN_TYPE_REFRESH

    def test_refresh_token_has_required_claims(self):
        token = create_refresh_token("user-456", "admin", 604800, self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert payload["sub"] == "user-456"
        assert payload["role"] == "admin"
        assert "jti" in payload
        assert "exp" in payload
        assert "iat" in payload
        assert "type" in payload

    def test_refresh_token_expired_raises(self):
        token = create_refresh_token("user-456", "admin", -1, self.SECRET)
        with pytest.raises(ZorkError) as exc_info:
            decode_token(token, self.SECRET)
        assert exc_info.value.status_code == 401


class TestVerifyTokenType:
    SECRET = "test-secret-key-for-testing"

    def test_verify_access_token_type_returns_true(self):
        token = create_access_token("user-123", "user", 3600, self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert verify_token_type(payload, TOKEN_TYPE_ACCESS) is True

    def test_verify_refresh_token_type_returns_true(self):
        token = create_refresh_token("user-123", "user", 3600, self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert verify_token_type(payload, TOKEN_TYPE_REFRESH) is True

    def test_verify_wrong_type_returns_false(self):
        token = create_access_token("user-123", "user", 3600, self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert verify_token_type(payload, TOKEN_TYPE_REFRESH) is False

    def test_verify_missing_type_returns_false(self):
        payload = {"sub": "user-123", "role": "user"}
        assert verify_token_type(payload, TOKEN_TYPE_ACCESS) is False


class TestTokenUniqueness:
    SECRET = "test-secret-key-for-testing"

    def test_access_tokens_have_unique_jti(self):
        t1 = create_access_token("user-123", "user", 3600, self.SECRET)
        t2 = create_access_token("user-123", "user", 3600, self.SECRET)
        p1 = decode_token(t1, self.SECRET)
        p2 = decode_token(t2, self.SECRET)
        assert p1["jti"] != p2["jti"]

    def test_refresh_tokens_have_unique_jti(self):
        t1 = create_refresh_token("user-123", "user", 604800, self.SECRET)
        t2 = create_refresh_token("user-123", "user", 604800, self.SECRET)
        p1 = decode_token(t1, self.SECRET)
        p2 = decode_token(t2, self.SECRET)
        assert p1["jti"] != p2["jti"]

    def test_access_and_refresh_have_different_jti(self):
        t1 = create_access_token("user-123", "user", 3600, self.SECRET)
        t2 = create_refresh_token("user-123", "user", 604800, self.SECRET)
        p1 = decode_token(t1, self.SECRET)
        p2 = decode_token(t2, self.SECRET)
        assert p1["jti"] != p2["jti"]


class TestTokenExpiry:
    SECRET = "test-secret-key-for-testing"

    def test_short_expiry_token(self):
        token = create_access_token("user-123", "user", 60, self.SECRET)
        payload = decode_token(token, self.SECRET)
        exp_time = payload["exp"]
        iat_time = payload["iat"]
        assert exp_time - iat_time == 60

    def test_long_expiry_token(self):
        token = create_refresh_token("user-123", "user", 2592000, self.SECRET)
        payload = decode_token(token, self.SECRET)
        exp_time = payload["exp"]
        iat_time = payload["iat"]
        assert exp_time - iat_time == 2592000


class TestLegacyCreateToken:
    SECRET = "test-secret-key-for-testing"

    def test_create_token_returns_access_token_type(self):
        token = create_token("user-123", "user", 3600, self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert payload["type"] == TOKEN_TYPE_ACCESS

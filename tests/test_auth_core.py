import pytest
from zeno.auth.passwords import hash_password, verify_password
from zeno.auth.tokens import create_token, decode_token
from zeno.errors import ZenoError


class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed = hash_password("mysecret")
        assert hashed != "mysecret"
        assert verify_password("mysecret", hashed) is True

    def test_wrong_password_fails(self):
        hashed = hash_password("mysecret")
        assert verify_password("wrongpass", hashed) is False

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2


class TestJWT:
    SECRET = "test-secret-key-for-testing"

    def test_create_and_decode_token(self):
        token = create_token("user-123", "user", 3600, self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert payload["sub"] == "user-123"
        assert payload["role"] == "user"
        assert "jti" in payload
        assert "exp" in payload
        assert "iat" in payload

    def test_expired_token_raises(self):
        token = create_token("user-123", "user", -1, self.SECRET)
        with pytest.raises(ZenoError) as exc_info:
            decode_token(token, self.SECRET)
        assert exc_info.value.status_code == 401

    def test_invalid_token_raises(self):
        with pytest.raises(ZenoError) as exc_info:
            decode_token("garbage.token.here", self.SECRET)
        assert exc_info.value.status_code == 401

    def test_wrong_secret_raises(self):
        token = create_token("user-123", "user", 3600, self.SECRET)
        with pytest.raises(ZenoError):
            decode_token(token, "wrong-secret")

    def test_tokens_have_unique_jti(self):
        t1 = create_token("user-123", "user", 3600, self.SECRET)
        t2 = create_token("user-123", "user", 3600, self.SECRET)
        p1 = decode_token(t1, self.SECRET)
        p2 = decode_token(t2, self.SECRET)
        assert p1["jti"] != p2["jti"]

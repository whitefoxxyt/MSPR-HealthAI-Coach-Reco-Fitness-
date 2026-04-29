import time
import pytest
from jose import jwt
from fastapi import HTTPException
from unittest.mock import patch

SECRET = "test_secret_for_unit_tests"
ALGORITHM = "HS256"


def _make_token(payload: dict, secret: str = SECRET) -> str:
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def _base_payload(offset: int = 3600) -> dict:
    return {
        "sub": "user-123",
        "email": "user@example.com",
        "exp": int(time.time()) + offset,
    }


@pytest.fixture(autouse=True)
def patch_secret():
    """Remplace BETTER_AUTH_SECRET par la valeur de test dans tous les tests."""
    with patch("app.services.jwt_decoder.settings") as mock_settings:
        mock_settings.BETTER_AUTH_SECRET = SECRET
        yield mock_settings


# ------------------------------------------------------------
# Import apres le patch pour eviter les effets de bord
# ------------------------------------------------------------
from app.services.jwt_decoder import decode, UserIdentity  # noqa: E402


class TestDecodeValid:
    def test_returns_user_identity(self):
        token = _make_token(_base_payload())
        identity = decode(token)
        assert isinstance(identity, UserIdentity)
        assert identity.user_id == "user-123"
        assert identity.email == "user@example.com"

    def test_email_none_when_absent(self):
        payload = {"sub": "user-456", "exp": int(time.time()) + 3600}
        token = _make_token(payload)
        identity = decode(token)
        assert identity.user_id == "user-456"
        assert identity.email is None


class TestDecodeInvalidSignature:
    def test_raises_401(self):
        token = _make_token(_base_payload(), secret="wrong_secret")
        with pytest.raises(HTTPException) as exc_info:
            decode(token)
        assert exc_info.value.status_code == 401

    def test_error_detail_mentions_invalide(self):
        token = _make_token(_base_payload(), secret="wrong_secret")
        with pytest.raises(HTTPException) as exc_info:
            decode(token)
        assert "invalide" in exc_info.value.detail.lower()


class TestDecodeExpired:
    def test_raises_401(self):
        token = _make_token(_base_payload(offset=-10))
        with pytest.raises(HTTPException) as exc_info:
            decode(token)
        assert exc_info.value.status_code == 401

    def test_error_detail_mentions_expire(self):
        token = _make_token(_base_payload(offset=-10))
        with pytest.raises(HTTPException) as exc_info:
            decode(token)
        assert "expir" in exc_info.value.detail.lower()


class TestDecodeMissingClaims:
    def test_missing_sub_raises_401(self):
        payload = {"email": "user@example.com", "exp": int(time.time()) + 3600}
        token = _make_token(payload)
        with pytest.raises(HTTPException) as exc_info:
            decode(token)
        assert exc_info.value.status_code == 401

    def test_error_detail_mentions_sub(self):
        payload = {"email": "user@example.com", "exp": int(time.time()) + 3600}
        token = _make_token(payload)
        with pytest.raises(HTTPException) as exc_info:
            decode(token)
        assert "sub" in exc_info.value.detail


class TestDecodeUnexpectedAlgorithm:
    def test_raises_401_for_rs256(self):
        """
        Un token signe avec un algorithme different de HS256 doit etre rejete.
        On simule en passant un token malforge (header algo modifie).
        """
        from jose.utils import base64url_encode
        import json

        header = base64url_encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        payload_b = base64url_encode(
            json.dumps({"sub": "user-123", "exp": int(time.time()) + 3600}).encode()
        )
        fake_token = f"{header.decode()}.{payload_b.decode()}.fakesignature"

        with pytest.raises(HTTPException) as exc_info:
            decode(fake_token)
        assert exc_info.value.status_code == 401

"""Unit tests for `validate_lambda_jwt` — call the dependency directly, no HTTP."""

import time
from collections.abc import Iterator

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi import HTTPException
from ticketmaster.http.v1.dependencies import _PublicAWSKeyCache, validate_lambda_jwt


def _make_keypair() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _public_pem(private_key: RSAPrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _sign_jwt(private_key: RSAPrivateKey, *, exp_offset: int = 60) -> str:
    now = int(time.time())
    return jwt.encode(
        payload={
            "iss": "ticketmaster-cognito-pre-signup",
            "sub": "arn:aws:iam::000000000000:role/ticketmaster-cognito-pre-signup",
            "aud": "ticketmaster-backend",
            "iat": now,
            "exp": now + exp_offset,
        },
        key=private_key,
        algorithm="PS256",
    )


@pytest.fixture
def signing_key_with_cached_public_key() -> Iterator[RSAPrivateKey]:
    private_key = _make_keypair()
    _PublicAWSKeyCache._cached_pem = _public_pem(private_key)
    yield private_key
    _PublicAWSKeyCache._cached_pem = None


@pytest.mark.asyncio(loop_scope="session")
async def test_validate_lambda_jwt_when_valid_token_passes(
    signing_key_with_cached_public_key: RSAPrivateKey,
) -> None:
    token = _sign_jwt(signing_key_with_cached_public_key)

    await validate_lambda_jwt(authorization=f"Bearer {token}")


@pytest.mark.asyncio(loop_scope="session")
async def test_validate_lambda_jwt_when_authorization_not_bearer_raises_401() -> None:
    with pytest.raises(HTTPException) as excinfo:
        await validate_lambda_jwt(authorization="Basic something")

    assert excinfo.value.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_validate_lambda_jwt_when_token_invalid_raises_401(
    signing_key_with_cached_public_key: RSAPrivateKey,
) -> None:
    """Expired token stands in for the whole 'pyjwt rejected this' family
    (also covers wrong-aud, wrong-iss, alg=none — same code path)."""
    token = _sign_jwt(signing_key_with_cached_public_key, exp_offset=-10)

    with pytest.raises(HTTPException) as excinfo:
        await validate_lambda_jwt(authorization=f"Bearer {token}")

    assert excinfo.value.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_validate_lambda_jwt_when_kms_key_was_rotated_passes_after_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache holds the old key; KMS now returns the new key; signed-by-new-key request succeeds
    after the refresh-once-on-InvalidSignature path."""
    old_key = _make_keypair()
    new_key = _make_keypair()
    _PublicAWSKeyCache._cached_pem = _public_pem(old_key)
    monkeypatch.setattr(
        _PublicAWSKeyCache,
        "_fetch_from_kms",
        classmethod(lambda cls: _public_pem(new_key)),
    )

    try:
        token = _sign_jwt(new_key)
        await validate_lambda_jwt(authorization=f"Bearer {token}")
    finally:
        _PublicAWSKeyCache._cached_pem = None

"""Unit tests for `validate_admin_jwt` — call the dependency directly, no HTTP."""

import time
from collections.abc import Iterator

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi import HTTPException
from ticketmaster.admin.http.dependencies import _cache, validate_admin_jwt
from ticketmaster.settings import settings


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
            "iss": settings.admin_jwt_issuer,
            "sub": "arn:aws:iam::000000000000:role/ticketmaster-admin",
            "aud": settings.jwt_audience,
            "iat": now,
            "exp": now + exp_offset,
        },
        key=private_key,
        algorithm="PS256",
    )


@pytest.fixture
def signing_key_with_cached_public_key() -> Iterator[RSAPrivateKey]:
    private_key = _make_keypair()
    _cache._cached_pem = _public_pem(private_key)
    yield private_key
    _cache._cached_pem = None


@pytest.mark.asyncio(loop_scope="session")
async def test_validate_admin_jwt_when_valid_token_passes(
    signing_key_with_cached_public_key: RSAPrivateKey,
) -> None:
    token = _sign_jwt(signing_key_with_cached_public_key)

    await validate_admin_jwt(authorization=f"Bearer {token}")


@pytest.mark.asyncio(loop_scope="session")
async def test_validate_admin_jwt_when_authorization_not_bearer_raises_401() -> None:
    with pytest.raises(HTTPException) as excinfo:
        await validate_admin_jwt(authorization="Basic something")

    assert excinfo.value.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_validate_admin_jwt_when_token_invalid_raises_401(
    signing_key_with_cached_public_key: RSAPrivateKey,
) -> None:
    """Expired token stands in for the whole 'pyjwt rejected this' family
    (also covers wrong-aud, wrong-iss, alg=none — same code path)."""
    token = _sign_jwt(signing_key_with_cached_public_key, exp_offset=-10)

    with pytest.raises(HTTPException) as excinfo:
        await validate_admin_jwt(authorization=f"Bearer {token}")

    assert excinfo.value.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_validate_admin_jwt_when_signed_by_other_key_raises_401(
    monkeypatch: pytest.MonkeyPatch,
    signing_key_with_cached_public_key: RSAPrivateKey,
) -> None:
    """A token signed by a different key (e.g. the lambda KMS key) fails signature
    verification against the admin key — proves the separate-key boundary. Pin the
    refresh path to the admin key so the retry stays offline and still fails."""
    admin_pem = _public_pem(signing_key_with_cached_public_key)

    async def _fake_fetch() -> bytes:
        return admin_pem

    monkeypatch.setattr(_cache, "_fetch_from_kms", _fake_fetch)

    other_key = _make_keypair()
    token = _sign_jwt(other_key)

    with pytest.raises(HTTPException) as excinfo:
        await validate_admin_jwt(authorization=f"Bearer {token}")

    assert excinfo.value.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_validate_admin_jwt_when_kms_key_was_rotated_passes_after_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache holds the old key; KMS now returns the new key; signed-by-new-key request
    succeeds after the refresh-once-on-InvalidSignature path."""
    old_key = _make_keypair()
    new_key = _make_keypair()
    _cache._cached_pem = _public_pem(old_key)

    async def _fake_fetch() -> bytes:
        return _public_pem(new_key)

    monkeypatch.setattr(_cache, "_fetch_from_kms", _fake_fetch)

    try:
        token = _sign_jwt(new_key)
        await validate_admin_jwt(authorization=f"Bearer {token}")
    finally:
        _cache._cached_pem = None

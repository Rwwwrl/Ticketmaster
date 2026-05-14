"""Unit tests for `validate_lambda_jwt` and `validate_user_jwt` — call the dependency directly, no HTTP."""

import json
import time
from collections.abc import Iterator

import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi import HTTPException
from httpx import Response
from jwt.algorithms import RSAAlgorithm
from libs.tests_ext.factories import insert
from sqlalchemy.ext.asyncio import AsyncEngine
from ticketmaster.http.v1.dependencies import (
    _cache,
    _cognito_cache,
    validate_lambda_jwt,
    validate_user_jwt,
)
from ticketmaster.settings import settings
from ticketmaster.tests.factories import UserFactory


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
    _cache._cached_pem = _public_pem(private_key)
    yield private_key
    _cache._cached_pem = None


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
    _cache._cached_pem = _public_pem(old_key)

    async def _fake_fetch() -> bytes:
        return _public_pem(new_key)

    monkeypatch.setattr(_cache, "_fetch_from_kms", _fake_fetch)

    try:
        token = _sign_jwt(new_key)
        await validate_lambda_jwt(authorization=f"Bearer {token}")
    finally:
        _cache._cached_pem = None


_COGNITO_KID = "test-kid"
_COGNITO_POOL_ID = "eu-central-1_testpool"


def _cognito_issuer(pool_id: str = _COGNITO_POOL_ID) -> str:
    return f"https://cognito-idp.{settings.aws_region}.amazonaws.com/{pool_id}"


def _jwks_url(pool_id: str = _COGNITO_POOL_ID) -> str:
    return f"{_cognito_issuer(pool_id=pool_id)}/.well-known/jwks.json"


def _build_jwks(private_key: RSAPrivateKey, kid: str = _COGNITO_KID) -> dict:
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = kid
    jwk["alg"] = "RS256"
    jwk["use"] = "sig"
    return {"keys": [jwk]}


def _sign_cognito_jwt(
    private_key: RSAPrivateKey,
    *,
    sub: str,
    pool_id: str = _COGNITO_POOL_ID,
    kid: str = _COGNITO_KID,
    token_use: str = "id",
    exp_offset: int = 60,
) -> str:
    now = int(time.time())
    return jwt.encode(
        payload={
            "iss": _cognito_issuer(pool_id=pool_id),
            "sub": sub,
            "aud": settings.cognito_audience,
            "iat": now,
            "exp": now + exp_offset,
            "token_use": token_use,
        },
        key=private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


@pytest.fixture(autouse=True)
def _clear_cognito_cache() -> Iterator[None]:
    yield
    _cognito_cache._cached_keys = {}


@pytest.mark.asyncio(loop_scope="session")
async def test_validate_user_jwt_when_valid_token_and_user_exists_returns_dto(
    sqlmodel_engine: AsyncEngine,
    respx_mock: respx.MockRouter,
) -> None:
    private_key = _make_keypair()
    user = UserFactory.build(pool_id=_COGNITO_POOL_ID, external_id="cognito-sub-1")
    await insert(user)

    respx_mock.get(_jwks_url()).mock(return_value=Response(status_code=200, json=_build_jwks(private_key=private_key)))

    token = _sign_cognito_jwt(private_key, sub=user.external_id)

    dto = await validate_user_jwt(authorization=f"Bearer {token}")

    assert dto.external_id == user.external_id
    assert dto.pool_id == _COGNITO_POOL_ID


@pytest.mark.asyncio(loop_scope="session")
async def test_validate_user_jwt_when_token_invalid_raises_401() -> None:
    with pytest.raises(HTTPException) as excinfo:
        await validate_user_jwt(authorization="Bearer not-a-real-jwt")

    assert excinfo.value.status_code == 401

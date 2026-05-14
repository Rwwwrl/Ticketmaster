import asyncio

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from fastapi import Header, HTTPException, status
from jwt.algorithms import RSAAlgorithm
from libs.aws.session import aws_session
from libs.sqlmodel_ext import Session

from ticketmaster.exceptions import UserNotFoundException
from ticketmaster.repositories import UserRepository
from ticketmaster.schemas.dtos import BaseUserDTO
from ticketmaster.settings import settings

_JWT_ALGORITHM = "PS256"
_COGNITO_JWT_ALGORITHM = "RS256"


class _PublicAWSKeyCache:
    def __init__(self) -> None:
        self._cached_pem: bytes | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> bytes:
        # NOTE @sosov: double-checked locking. Fast path takes no lock — steady-state
        # every request hits the cache. The lock only matters during cold-start surge:
        # without it N concurrent first requests fire N parallel `kms:GetPublicKey`
        # calls which can hit the per-account KMS rate limit.
        if self._cached_pem is not None:
            return self._cached_pem

        async with self._lock:
            if self._cached_pem is None:
                self._cached_pem = await self._fetch_from_kms()
            return self._cached_pem

    async def get_force_refreshed(self) -> bytes:
        async with self._lock:
            self._cached_pem = await self._fetch_from_kms()
            return self._cached_pem

    async def _fetch_from_kms(self) -> bytes:
        async with aws_session.client(service_name="kms") as kms:
            response = await kms.get_public_key(KeyId=settings.lambda_jwt_kms_key_arn)

        public_key = serialization.load_der_public_key(data=response["PublicKey"])

        return public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )


_cache = _PublicAWSKeyCache()


def _decode_jwt_token(token: str, public_key: bytes) -> dict:
    return jwt.decode(
        jwt=token,
        key=public_key,
        algorithms=[_JWT_ALGORITHM],
        audience=settings.lambda_jwt_audience,
        issuer=settings.lambda_jwt_issuer,
        options={"require": ["exp", "iat", "iss", "aud"]},
    )


async def validate_lambda_jwt(authorization: str = Header(...)) -> None:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    token = authorization.split(" ", 1)[1]

    try:
        _decode_jwt_token(token=token, public_key=await _cache.get())
    except jwt.InvalidSignatureError:
        # NOTE @sosov: KMS key may have been rotated. Refresh once and retry.
        # Same self-healing pattern that JWKS clients (Auth0, Cognito) use.
        try:
            _decode_jwt_token(token=token, public_key=await _cache.get_force_refreshed())
        except jwt.PyJWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


_COGNITO_ISSUER_PREFIX = "https://cognito-idp."
_COGNITO_ISSUER_SUFFIX = ".amazonaws.com/"


def _extract_pool_id_from_issuer(issuer: str) -> str:
    expected_prefix = f"{_COGNITO_ISSUER_PREFIX}{settings.aws_region}{_COGNITO_ISSUER_SUFFIX}"

    if not issuer.startswith(expected_prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    pool_id = issuer[len(expected_prefix) :]
    if not pool_id or "/" in pool_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return pool_id


class _CognitoJWKSCache:
    def __init__(self) -> None:
        self._cached_keys: dict[tuple[str, str], bytes] = {}
        self._lock = asyncio.Lock()

    async def get(self, pool_id: str, kid: str) -> bytes | None:
        # NOTE @sosov: double-checked locking — same shape as _PublicAWSKeyCache.
        # Steady-state requests skip the lock; cold-start surges collapse to a single fetch.
        cache_key = (pool_id, kid)
        if cache_key in self._cached_keys:
            return self._cached_keys[cache_key]

        async with self._lock:
            if cache_key not in self._cached_keys:
                await self._fetch_and_cache(pool_id=pool_id)

            return self._cached_keys.get(cache_key)

    async def get_force_refreshed(self, pool_id: str, kid: str) -> bytes:
        async with self._lock:
            await self._fetch_and_cache(pool_id=pool_id)
        return self._cached_keys[(pool_id, kid)]

    async def _fetch_and_cache(self, pool_id: str) -> None:
        url = f"{_COGNITO_ISSUER_PREFIX}{settings.aws_region}{_COGNITO_ISSUER_SUFFIX}{pool_id}/.well-known/jwks.json"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            jwks = response.json()

        for jwk in jwks["keys"]:
            public_key = RSAAlgorithm.from_jwk(jwk)
            self._cached_keys[(pool_id, jwk["kid"])] = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )


_cognito_cache = _CognitoJWKSCache()


def _decode_cognito_jwt_token(token: str, public_key: bytes, issuer: str) -> dict:
    return jwt.decode(
        jwt=token,
        key=public_key,
        algorithms=[_COGNITO_JWT_ALGORITHM],
        audience=settings.cognito_audience,
        issuer=issuer,
        options={"require": ["exp", "iat", "iss", "aud", "sub", "token_use"]},
    )


async def _resolve_cognito_claims(token: str) -> tuple[dict, str]:
    try:
        unverified_header = jwt.get_unverified_header(jwt=token)
        unverified_claims = jwt.decode(jwt=token, options={"verify_signature": False})
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    kid = unverified_header.get("kid")
    issuer = unverified_claims.get("iss")
    if not isinstance(kid, str) or not isinstance(issuer, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    pool_id = _extract_pool_id_from_issuer(issuer=issuer)

    try:
        public_key = await _cognito_cache.get(pool_id=pool_id, kid=kid)
    except httpx.HTTPError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    if public_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        claims = _decode_cognito_jwt_token(token=token, public_key=public_key, issuer=issuer)
    except jwt.InvalidSignatureError:
        # NOTE @sosov: Cognito rotates signing keys. Refresh once and retry.
        try:
            refreshed_key = await _cognito_cache.get_force_refreshed(pool_id=pool_id, kid=kid)
            claims = _decode_cognito_jwt_token(token=token, public_key=refreshed_key, issuer=issuer)
        except jwt.PyJWTError, httpx.HTTPError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return claims, pool_id


async def validate_user_jwt(authorization: str = Header(...)) -> BaseUserDTO:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    claims, pool_id = await _resolve_cognito_claims(token=authorization.split(" ", 1)[1])

    if claims.get("token_use") != "id":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    async with Session() as session, session.begin():
        try:
            return await UserRepository.get_by_pool_and_external_id(
                session=session,
                pool_id=pool_id,
                external_id=claims["sub"],
            )
        except UserNotFoundException:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

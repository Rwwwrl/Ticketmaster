import asyncio
from typing import Annotated

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from fastapi import Header, HTTPException, Query, status
from jwt.algorithms import RSAAlgorithm
from libs.aws.kms_public_key_cache import KMSPublicKeyCache
from libs.common.services import decode_service_cursor
from libs.sqlmodel_ext import Session

from ticketmaster.cursors import EventCursorDTO
from ticketmaster.enums import EventSortKeyEnum
from ticketmaster.exceptions import UserNotFoundException
from ticketmaster.repositories import UserRepository
from ticketmaster.schemas.dtos import BaseUserDTO
from ticketmaster.settings import settings


def decode_event_cursor(
    sort_key: Annotated[EventSortKeyEnum, Query()],
    cursor: Annotated[str | None, Query()] = None,
) -> EventCursorDTO | None:
    if cursor is None:
        return None

    try:
        decoded_cursor = decode_service_cursor(
            encoded_cursor=cursor,
            cursor_class=EventCursorDTO,
            secret=settings.secret,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid cursor") from exc

    if decoded_cursor.body.sort_key != sort_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cursor does not match sort_key")

    return decoded_cursor


_JWT_ALGORITHM = "PS256"
_COGNITO_JWT_ALGORITHM = "RS256"


_cache = KMSPublicKeyCache(key_arn=settings.lambda_jwt_kms_key_arn)


def _decode_jwt_token(token: str, public_key: bytes) -> dict:
    return jwt.decode(
        jwt=token,
        key=public_key,
        algorithms=[_JWT_ALGORITHM],
        audience=settings.jwt_audience,
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

    cognito_username = claims.get("cognito:username")
    if not isinstance(cognito_username, str) or not cognito_username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    async with Session() as session, session.begin():
        try:
            return await UserRepository.get_by_pool_and_cognito_username(
                session=session,
                pool_id=pool_id,
                cognito_username=cognito_username,
            )
        except UserNotFoundException:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

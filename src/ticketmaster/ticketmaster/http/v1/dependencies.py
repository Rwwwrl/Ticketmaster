import asyncio

import jwt
from cryptography.hazmat.primitives import serialization
from fastapi import Header, HTTPException, status
from libs.aws.session import aws_session

from ticketmaster.settings import settings

_JWT_ALGORITHM = "PS256"


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

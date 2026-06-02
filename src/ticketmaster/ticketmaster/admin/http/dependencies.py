import jwt
from fastapi import Header, HTTPException, status
from libs.aws.kms_public_key_cache import KMSPublicKeyCache

from ticketmaster.settings import settings

_ADMIN_JWT_ALGORITHM = "PS256"

_cache = KMSPublicKeyCache(key_arn=settings.admin_jwt_kms_key_arn)


def _decode_jwt_token(token: str, public_key: bytes) -> dict:
    return jwt.decode(
        jwt=token,
        key=public_key,
        algorithms=[_ADMIN_JWT_ALGORITHM],
        audience=settings.jwt_audience,
        issuer=settings.admin_jwt_issuer,
        options={"require": ["exp", "iat", "iss", "aud"]},
    )


async def validate_admin_jwt(authorization: str = Header(...)) -> None:
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

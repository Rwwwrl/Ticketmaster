import boto3
import jwt
from cryptography.hazmat.primitives import serialization
from fastapi import Header, HTTPException, status

from ticketmaster.settings import settings

_JWT_ALGORITHM = "PS256"


class _PublicAWSKeyCache:
    _cached_pem: bytes | None = None

    @classmethod
    def get(cls) -> bytes:
        if cls._cached_pem is None:
            cls._cached_pem = cls._fetch_from_kms()
        return cls._cached_pem

    @classmethod
    def get_force_refreshed(cls) -> bytes:
        cls._cached_pem = cls._fetch_from_kms()
        return cls._cached_pem

    @classmethod
    def _fetch_from_kms(cls) -> bytes:
        kms = boto3.client(service_name="kms", region_name=settings.aws_region)
        response = kms.get_public_key(KeyId=settings.lambda_jwt_kms_key_arn)
        public_key = serialization.load_der_public_key(data=response["PublicKey"])
        return public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )


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
        _decode_jwt_token(token=token, public_key=_PublicAWSKeyCache.get())
    except jwt.InvalidSignatureError:
        # NOTE @sosov: KMS key may have been rotated. Refresh once and retry.
        # Same self-healing pattern that JWKS clients (Auth0, Cognito) use.
        try:
            _decode_jwt_token(token=token, public_key=_PublicAWSKeyCache.get_force_refreshed())
        except jwt.PyJWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

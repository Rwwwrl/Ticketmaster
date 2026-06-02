import asyncio
import base64
import json
import sys
import time

from libs.aws.session import aws_session

from ticketmaster.settings import settings

_JWT_ALGORITHM = "PS256"
_JWT_TTL_SECONDS = 900


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


async def create_admin_jwt() -> None:
    now = int(time.time())

    async with aws_session.client(service_name="sts", region_name=settings.aws_region) as sts:
        identity = await sts.get_caller_identity()

    header = {"alg": _JWT_ALGORITHM, "typ": "JWT"}
    claims = {
        "iss": settings.admin_jwt_issuer,
        "sub": identity["Arn"],
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + _JWT_TTL_SECONDS,
    }
    signing_input = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(claims).encode())}"

    async with aws_session.client(service_name="kms", region_name=settings.aws_region) as kms:
        response = await kms.sign(
            KeyId=settings.admin_jwt_kms_key_arn,
            Message=signing_input.encode(),
            MessageType="RAW",
            SigningAlgorithm="RSASSA_PSS_SHA_256",
        )

    token = f"{signing_input}.{_b64url(response['Signature'])}"

    print(token)
    print(f"Admin JWT for {identity['Arn']}, expires in {_JWT_TTL_SECONDS // 60} minutes.", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(create_admin_jwt())

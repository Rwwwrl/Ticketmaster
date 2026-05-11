import base64
import json
import os
import time
import uuid

import boto3
import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

API_URL = os.environ["TICKETMASTER_API_URL"]
AWS_REGION = os.environ["AWS_REGION"]
KMS_KEY_ARN = os.environ["JWT_KMS_KEY_ARN"]
JWT_AUDIENCE = os.environ["JWT_AUDIENCE"]
JWT_ISSUER = os.environ["JWT_ISSUER"]

# NOTE @sosov: AWS does not expose the Lambda's own execution role ARN through any runtime API
# or env var (unlike GCP, where the metadata server hands you the SA email), so we pass it
# explicitly.
LAMBDA_ROLE_ARN = os.environ["LAMBDA_ROLE_ARN"]

TIMEOUT_SECONDS = 5.0
JWT_TTL_SECONDS = 60
JWT_ALGORITHM = "PS256"

_kms = boto3.client(service_name="kms", region_name=AWS_REGION)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _build_jwt() -> str:
    now = int(time.time())
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    claims = {
        "iss": JWT_ISSUER,
        "sub": LAMBDA_ROLE_ARN,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    }
    signing_input = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(claims).encode())}"
    response = _kms.sign(
        KeyId=KMS_KEY_ARN,
        Message=signing_input.encode(),
        MessageType="RAW",
        SigningAlgorithm="RSASSA_PSS_SHA_256",
    )
    return f"{signing_input}.{_b64url(response['Signature'])}"


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return 500 <= exc.response.status_code < 600
    return isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError))


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, min=0.2, max=1.0),
    reraise=True,
)
def _post_to_backend(payload: dict) -> None:
    response = httpx.post(
        url=f"{API_URL}/v1/users/",
        json=payload,
        headers={"Authorization": f"Bearer {_build_jwt()}"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()


def lambda_handler(event: dict, context) -> dict:
    payload = {
        "uuid": str(uuid.uuid4()),
        "email": event["request"]["userAttributes"]["email"],
        "external_id": event["userName"],
        "pool_id": event["userPoolId"],
    }
    _post_to_backend(payload=payload)
    return event

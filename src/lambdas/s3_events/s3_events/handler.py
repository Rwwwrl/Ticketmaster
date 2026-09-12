import base64
import json
import os
import time
import urllib.parse
from http import HTTPStatus

import boto3
import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

API_URL = os.environ["TICKETMASTER_API_URL"]
AWS_REGION = os.environ["AWS_REGION"]
KMS_KEY_ARN = os.environ["S3_EVENTS_JWT_KMS_KEY_ARN"]
JWT_AUDIENCE = os.environ["JWT_AUDIENCE"]
JWT_ISSUER = os.environ["S3_EVENTS_JWT_ISSUER"]

# NOTE @sosov: AWS does not expose the Lambda's own execution role ARN through any runtime API
# or env var (unlike GCP, where the metadata server hands you the SA email), so we pass it
# explicitly.
LAMBDA_ROLE_ARN = os.environ["LAMBDA_ROLE_ARN"]

TIMEOUT_SECONDS = 5.0
JWT_TTL_SECONDS = 60
JWT_ALGORITHM = "PS256"

_kms = boto3.client(service_name="kms", region_name=AWS_REGION)
_s3 = boto3.client(service_name="s3", region_name=AWS_REGION)


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


_RETRYABLE_STATUS_CODES = (HTTPStatus.REQUEST_TIMEOUT, HTTPStatus.TOO_MANY_REQUESTS)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code >= 500 or status_code in _RETRYABLE_STATUS_CODES
    return isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError))


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, min=0.2, max=1.0),
    reraise=True,
)
def _post_to_backend(payload: dict) -> None:
    response = httpx.post(
        url=f"{API_URL}/api/admin/s3-events",
        json=payload,
        headers={"Authorization": f"Bearer {_build_jwt()}"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()


def lambda_handler(event: dict, context) -> dict:
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        head = _s3.head_object(Bucket=bucket, Key=key)
        metadata = head["Metadata"]

        _post_to_backend(payload={"bucket": bucket, "key": key, "metadata": metadata})

    return {"status": "ok"}

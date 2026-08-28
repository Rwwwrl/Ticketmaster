import json
import time
from unittest.mock import MagicMock, patch

import httpx
import jwt
import pytest
import respx
from cognito_pre_signup import handler
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.hashes import SHA256
from httpx import Response

_EVENT = {
    "userPoolId": "eu-central-1_aB12cDEFg",
    "userName": "alice@example.com",
    "request": {"userAttributes": {"email": "alice@example.com"}},
}

_BACKEND_URL = "https://ticketmaster.test.invalid/api/v1/users/"


def _make_keypair() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _public_pem(private_key: RSAPrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _build_kms_stub(private_key: RSAPrivateKey) -> MagicMock:
    """Stub of boto3 KMS client whose `sign(...)` produces an RSASSA-PSS / SHA-256 signature
    over the given message — matching real KMS RSASSA_PSS_SHA_256 and PyJWT's PS256 verifier."""
    stub = MagicMock()

    def _sign(*, KeyId, Message, MessageType, SigningAlgorithm) -> dict:
        signature = private_key.sign(
            data=Message,
            padding=padding.PSS(mgf=padding.MGF1(SHA256()), salt_length=SHA256.digest_size),
            algorithm=SHA256(),
        )
        return {"Signature": signature, "KeyId": KeyId, "SigningAlgorithm": SigningAlgorithm}

    stub.sign.side_effect = _sign
    return stub


@respx.mock
def test_handler_posts_payload_and_signed_jwt_on_success() -> None:
    private_key = _make_keypair()
    captured: dict = {}

    def _capture(request) -> Response:
        captured["body"] = request.read()
        captured["auth"] = request.headers["authorization"]
        return Response(status_code=201, json={})

    respx.post(_BACKEND_URL).mock(side_effect=_capture)

    with patch.object(handler, "_kms", _build_kms_stub(private_key)):
        result = handler.lambda_handler(event=_EVENT, context=None)

    assert result is _EVENT

    body = json.loads(captured["body"])
    assert body["email"] == "alice@example.com"
    assert body["cognito_username"] == "alice@example.com"
    assert body["pool_id"] == "eu-central-1_aB12cDEFg"
    assert "uuid" in body

    assert captured["auth"].startswith("Bearer ")
    token = captured["auth"].split(" ", 1)[1]
    claims = jwt.decode(
        jwt=token,
        key=_public_pem(private_key),
        algorithms=["PS256"],
        audience="ticketmaster-backend",
        issuer="ticketmaster-cognito-pre-signup",
    )
    assert claims["exp"] - claims["iat"] == 60
    assert claims["iat"] <= int(time.time())


@respx.mock
def test_handler_does_not_retry_on_4xx() -> None:
    route = respx.post(_BACKEND_URL).mock(return_value=Response(status_code=400))

    with patch.object(handler, "_kms", _build_kms_stub(_make_keypair())):
        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            handler.lambda_handler(event=_EVENT, context=None)

    assert excinfo.value.response.status_code == 400
    assert route.call_count == 1


@respx.mock
def test_handler_retries_on_5xx_then_raises_after_max_attempts() -> None:
    route = respx.post(_BACKEND_URL).mock(return_value=Response(status_code=503))

    with patch.object(handler, "_kms", _build_kms_stub(_make_keypair())):
        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            handler.lambda_handler(event=_EVENT, context=None)

    assert excinfo.value.response.status_code == 503
    assert route.call_count == 3

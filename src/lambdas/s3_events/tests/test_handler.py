import json
import time
from unittest.mock import MagicMock, patch

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.hashes import SHA256
from httpx import Response
from s3_events import handler

_BUCKET = "ticketmaster-test-eu-media"
_BACKEND_URL = "https://ticketmaster.test.invalid/api/admin/s3-events"
_METADATA = {"kind": "event-trailer", "logical-identity": "3fa85f64-5717-4562-b3fc-2c963f66afa6"}


def _s3_event(*keys: str) -> dict:
    return {"Records": [{"s3": {"bucket": {"name": _BUCKET}, "object": {"key": key}}} for key in keys]}


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


def _build_s3_stub(metadata_by_key: dict[str, dict[str, str]] | None = None) -> MagicMock:
    stub = MagicMock()
    metadata_by_key = metadata_by_key or {}

    def _head_object(*, Bucket, Key) -> dict:
        return {"Metadata": metadata_by_key.get(Key, _METADATA)}

    stub.head_object.side_effect = _head_object
    return stub


@respx.mock
def test_handler_posts_payload_and_signed_jwt_on_success() -> None:
    private_key = _make_keypair()
    captured: dict = {}

    def _capture(request) -> Response:
        captured["body"] = request.read()
        captured["auth"] = request.headers["authorization"]
        return Response(status_code=204)

    respx.post(_BACKEND_URL).mock(side_effect=_capture)

    key = "event-trailer/9f3cd1.mp4"
    with (
        patch.object(handler, "_kms", _build_kms_stub(private_key)),
        patch.object(handler, "_s3", _build_s3_stub({key: _METADATA})),
    ):
        result = handler.lambda_handler(event=_s3_event(key), context=None)

    assert result == {"status": "ok"}

    body = json.loads(captured["body"])
    assert body == {"bucket": _BUCKET, "key": key, "metadata": _METADATA}

    assert captured["auth"].startswith("Bearer ")
    token = captured["auth"].split(" ", 1)[1]
    claims = jwt.decode(
        jwt=token,
        key=_public_pem(private_key),
        algorithms=["PS256"],
        audience="ticketmaster-backend",
        issuer="ticketmaster-s3-events",
    )
    assert claims["exp"] - claims["iat"] == 60
    assert claims["iat"] <= int(time.time())


@respx.mock
def test_handler_multiple_records_heads_and_posts_each_one() -> None:
    keys = ("event-trailer/one.mp4", "event-trailer/two.mp4")
    route = respx.post(_BACKEND_URL).mock(return_value=Response(status_code=204))

    s3_stub = _build_s3_stub(
        {
            keys[0]: {"kind": "event-trailer", "logical-identity": "a"},
            keys[1]: {"kind": "event-trailer", "logical-identity": "b"},
        }
    )

    with patch.object(handler, "_kms", _build_kms_stub(_make_keypair())), patch.object(handler, "_s3", s3_stub):
        result = handler.lambda_handler(event=_s3_event(*keys), context=None)

    assert result == {"status": "ok"}
    assert route.call_count == 2
    assert s3_stub.head_object.call_count == 2

    posted_keys = {json.loads(call.request.read())["key"] for call in route.calls}
    assert posted_keys == set(keys)


@respx.mock
def test_handler_decodes_url_encoded_key_before_head_object_and_post() -> None:
    encoded_key = "event-trailer/my+file%241.mp4"
    decoded_key = "event-trailer/my file$1.mp4"
    captured: dict = {}

    def _capture(request) -> Response:
        captured["body"] = request.read()
        return Response(status_code=204)

    respx.post(_BACKEND_URL).mock(side_effect=_capture)
    s3_stub = _build_s3_stub({decoded_key: _METADATA})

    with patch.object(handler, "_kms", _build_kms_stub(_make_keypair())), patch.object(handler, "_s3", s3_stub):
        handler.lambda_handler(event=_s3_event(encoded_key), context=None)

    s3_stub.head_object.assert_called_once_with(Bucket=_BUCKET, Key=decoded_key)
    assert json.loads(captured["body"])["key"] == decoded_key


@respx.mock
def test_handler_does_not_retry_on_4xx() -> None:
    route = respx.post(_BACKEND_URL).mock(return_value=Response(status_code=400))

    with (
        patch.object(handler, "_kms", _build_kms_stub(_make_keypair())),
        patch.object(handler, "_s3", _build_s3_stub()),
        pytest.raises(httpx.HTTPStatusError) as excinfo,
    ):
        handler.lambda_handler(event=_s3_event("event-trailer/x.mp4"), context=None)

    assert excinfo.value.response.status_code == 400
    assert route.call_count == 1


@respx.mock
def test_handler_retries_on_429_then_raises_after_max_attempts() -> None:
    route = respx.post(_BACKEND_URL).mock(return_value=Response(status_code=429))

    with (
        patch.object(handler, "_kms", _build_kms_stub(_make_keypair())),
        patch.object(handler, "_s3", _build_s3_stub()),
        pytest.raises(httpx.HTTPStatusError) as excinfo,
    ):
        handler.lambda_handler(event=_s3_event("event-trailer/x.mp4"), context=None)

    assert excinfo.value.response.status_code == 429
    assert route.call_count == 3


@respx.mock
def test_handler_retries_on_5xx_then_raises_after_max_attempts() -> None:
    route = respx.post(_BACKEND_URL).mock(return_value=Response(status_code=503))

    with (
        patch.object(handler, "_kms", _build_kms_stub(_make_keypair())),
        patch.object(handler, "_s3", _build_s3_stub()),
        pytest.raises(httpx.HTTPStatusError) as excinfo,
    ):
        handler.lambda_handler(event=_s3_event("event-trailer/x.mp4"), context=None)

    assert excinfo.value.response.status_code == 503
    assert route.call_count == 3

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from libs.aws.session import aws_session
from libs.tests_ext.factories import insert
from ticketmaster.admin.http.schemas.response_schemas import EventTrailerUploadLinkResponseSchema
from ticketmaster.enums import S3BucketEnum
from ticketmaster.tests.factories import EventFactory

_FAKE_UPLOAD_URL = "https://ticketmaster-test-eu-media-public.s3.eu-central-1.amazonaws.com/event-trailer/fake.mp4"


@pytest.fixture
def mock_s3(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    s3 = AsyncMock()
    s3.generate_presigned_url = AsyncMock(return_value=_FAKE_UPLOAD_URL)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=s3)
    cm.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(aws_session, "client", MagicMock(return_value=cm))
    return s3


@pytest.mark.asyncio(loop_scope="session")
async def test_create_event_trailer_upload_link_when_event_exists_returns_200(
    async_client: AsyncClient,
    bypass_admin_jwt: None,
    mock_s3: AsyncMock,
) -> None:
    event = EventFactory()
    await insert(event)

    response = await async_client.post(url=f"/api/admin/events/{event.id}/trailer/upload-link")

    assert response.status_code == 200
    body = EventTrailerUploadLinkResponseSchema(**response.json())
    assert body.upload_url == _FAKE_UPLOAD_URL
    assert body.headers["Content-Type"] == "video/mp4"
    assert body.headers["x-amz-meta-kind"] == "event-trailer"
    assert body.headers["x-amz-meta-logical-identity"] == str(event.logical_identity)

    mock_s3.generate_presigned_url.assert_awaited_once()
    _, kwargs = mock_s3.generate_presigned_url.await_args
    assert kwargs["ClientMethod"] == "put_object"
    assert kwargs["ExpiresIn"] == 900

    params = kwargs["Params"]
    assert params["Bucket"] == S3BucketEnum.MEDIA_PUBLIC.value
    assert params["Key"].startswith("event-trailer/")
    assert params["Key"].endswith(".mp4")
    assert params["ContentType"] == "video/mp4"
    assert params["Metadata"] == {"kind": "event-trailer", "logical-identity": str(event.logical_identity)}


@pytest.mark.asyncio(loop_scope="session")
async def test_create_event_trailer_upload_link_when_event_not_found_returns_404(
    async_client: AsyncClient,
    bypass_admin_jwt: None,
    mock_s3: AsyncMock,
) -> None:
    response = await async_client.post(url="/api/admin/events/999999/trailer/upload-link")

    assert response.status_code == 404
    mock_s3.generate_presigned_url.assert_not_awaited()

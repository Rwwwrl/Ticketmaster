from uuid import uuid4

from libs.aws.session import aws_session
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.admin.enums import S3EventKindEnum
from ticketmaster.admin.http.schemas.response_schemas import EventTrailerUploadLinkResponseSchema
from ticketmaster.enums import S3BucketEnum
from ticketmaster.repositories import EventRepository


async def create_event_trailer_upload_link(
    session: AsyncSession,
    event_id: int,
) -> EventTrailerUploadLinkResponseSchema:
    event = await EventRepository.get_by_id(session=session, _id=event_id)

    key = f"{S3EventKindEnum.EVENT_TRAILER.value}/{uuid4()}.mp4"
    metadata = {"kind": S3EventKindEnum.EVENT_TRAILER.value, "logical-identity": str(event.logical_identity)}

    async with aws_session.client(service_name="s3") as s3:
        upload_url = await s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": S3BucketEnum.MEDIA_PUBLIC.value,
                "Key": key,
                "ContentType": "video/mp4",
                "Metadata": metadata,
            },
            ExpiresIn=900,
        )

    headers = {"Content-Type": "video/mp4"}
    headers.update({f"x-amz-meta-{name}": value for name, value in metadata.items()})

    return EventTrailerUploadLinkResponseSchema(upload_url=upload_url, headers=headers)

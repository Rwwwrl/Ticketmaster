from libs.fastapi_ext.schemas.base_schemas import BaseResponseSchema


class EventTrailerUploadLinkResponseSchema(BaseResponseSchema):
    upload_url: str
    headers: dict[str, str]

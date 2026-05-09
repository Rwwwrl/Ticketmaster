from uuid import UUID

from libs.fastapi_ext.schemas.base_schemas import BaseRequestSchema
from pydantic import EmailStr


class CreateUserFallbackRequestSchema(BaseRequestSchema):
    uuid: UUID
    email: EmailStr
    external_id: str
    pool_id: str

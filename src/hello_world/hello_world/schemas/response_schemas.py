from libs.common.enums import EnvironmentEnum
from libs.fastapi_ext.schemas.base_schemas import BaseResponseSchema


class HelloWorldResponseSchema(BaseResponseSchema):
    message: str
    environment: EnvironmentEnum
    secret_fingerprint: str

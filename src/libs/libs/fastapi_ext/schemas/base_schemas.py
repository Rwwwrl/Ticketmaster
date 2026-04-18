from libs.common.schemas.dto import DTO


class BaseRequestSchema(DTO):
    """Schema for what an API endpoint accepts as input."""


class BaseResponseSchema(DTO):
    """Schema for what an API endpoint returns to the client."""

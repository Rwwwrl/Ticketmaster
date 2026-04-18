from pydantic import BaseModel, ConfigDict


class DTO(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

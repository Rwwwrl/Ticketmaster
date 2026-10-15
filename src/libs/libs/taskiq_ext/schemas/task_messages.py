from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from libs.datetime_ext.utils import utc_now

_TASK_MESSAGE_CODE_REGISTRY: dict[int, type] = {}


class BaseTaskMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    code: ClassVar[int]

    logical_id: UUID
    created_at: datetime = Field(default_factory=utc_now)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        try:
            code = cls.code
        except AttributeError:
            raise TypeError(f"{cls.__qualname__} must define a `code` class attribute")

        if code in _TASK_MESSAGE_CODE_REGISTRY:
            existing = _TASK_MESSAGE_CODE_REGISTRY[code]
            raise ValueError(
                f"Duplicate task message code {code}: {cls.__qualname__} conflicts with {existing.__qualname__}"
            )

        _TASK_MESSAGE_CODE_REGISTRY[code] = cls

    @model_serializer(mode="wrap")
    def _inject_code_into_output(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        data["code"] = type(self).code
        return data

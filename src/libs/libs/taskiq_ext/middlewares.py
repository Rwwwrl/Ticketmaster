import logging
import time
from typing import Any

from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from libs.context_vars import request_id_var

_REQUEST_ID_LABEL = "request_id"
_TIMEOUT_LABEL = "timeout"

_logger = logging.getLogger("taskiq.lifecycle")


class RequestIdMiddleware(TaskiqMiddleware):
    def pre_send(self, message: TaskiqMessage) -> TaskiqMessage:
        request_id = request_id_var.get()
        if request_id is not None:
            message.labels[_REQUEST_ID_LABEL] = request_id
        return message

    def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        request_id = message.labels.get(_REQUEST_ID_LABEL)
        if request_id is not None:
            request_id_var.set(str(request_id))
        return message


class TimeLimitMiddleware(TaskiqMiddleware):
    def __init__(self, default_timeout_seconds: float) -> None:
        super().__init__()
        self._default_timeout_seconds = default_timeout_seconds

    def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        message.labels.setdefault(_TIMEOUT_LABEL, self._default_timeout_seconds)
        return message


class TaskLifecycleLogMiddleware(TaskiqMiddleware):
    def __init__(self) -> None:
        super().__init__()
        self._started_at: dict[str, float] = {}

    def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        self._started_at[message.task_id] = time.monotonic()
        _logger.info("Task started", extra={"task_name": message.task_name, "task_id": message.task_id})
        return message

    def post_execute(self, message: TaskiqMessage, result: TaskiqResult[Any]) -> None:
        started_at = self._started_at.pop(message.task_id, None)
        duration_seconds = None if started_at is None else round(time.monotonic() - started_at, 3)
        extra = {
            "task_name": message.task_name,
            "task_id": message.task_id,
            "duration_seconds": duration_seconds,
        }
        if result.is_err:
            _logger.error("Task failed", extra=extra, exc_info=result.error)
        else:
            _logger.info("Task succeeded", extra=extra)

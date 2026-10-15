from typing import Any, get_type_hints

from taskiq import AsyncBroker
from taskiq.decor import AsyncTaskiqDecoratedTask

_TASK_MESSAGE_PARAMETER = "body"

type TasksByCode = dict[int, AsyncTaskiqDecoratedTask[Any, Any]]


def build_task_registry(broker: AsyncBroker) -> TasksByCode:
    tasks_by_code: TasksByCode = {}

    for task in broker.get_all_tasks().values():
        message_type = get_type_hints(task.original_func)[_TASK_MESSAGE_PARAMETER]
        existing = tasks_by_code.get(message_type.code)
        if existing is not None:
            raise ValueError(
                f"Tasks {existing.task_name} and {task.task_name} both take {message_type.__qualname__}"
                f" (code {message_type.code})"
            )

        tasks_by_code[message_type.code] = task

    return tasks_by_code

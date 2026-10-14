import logging
from collections.abc import Iterator

import pytest
from libs.context_vars import request_id_var
from libs.taskiq_ext import RequestIdMiddleware, TaskLifecycleLogMiddleware, TimeLimitMiddleware
from taskiq import TaskiqMessage, TaskiqResult


def _make_message(labels: dict[str, str | float] | None = None) -> TaskiqMessage:
    return TaskiqMessage(task_id="task-1", task_name="demo.task", labels=labels or {}, args=[], kwargs={})


def _make_result(is_err: bool, error: BaseException | None = None) -> TaskiqResult[None]:
    return TaskiqResult(is_err=is_err, return_value=None, execution_time=0.0, error=error)


@pytest.fixture(autouse=True)
def _reset_request_id() -> Iterator[None]:
    token = request_id_var.set(None)
    yield
    request_id_var.reset(token)


def test_request_id_pre_send_copies_var_into_label() -> None:
    request_id_var.set("req-1")

    message = RequestIdMiddleware().pre_send(message=_make_message())

    assert message.labels["request_id"] == "req-1"


def test_request_id_pre_send_without_var_adds_no_label() -> None:
    message = RequestIdMiddleware().pre_send(message=_make_message())

    assert "request_id" not in message.labels


def test_request_id_pre_execute_restores_var_from_label() -> None:
    RequestIdMiddleware().pre_execute(message=_make_message(labels={"request_id": "req-2"}))

    assert request_id_var.get() == "req-2"


def test_request_id_pre_execute_without_label_leaves_var_untouched() -> None:
    RequestIdMiddleware().pre_execute(message=_make_message())

    assert request_id_var.get() is None


def test_time_limit_sets_default_timeout_when_missing() -> None:
    message = TimeLimitMiddleware(default_timeout_seconds=60).pre_execute(message=_make_message())

    assert message.labels["timeout"] == 60


def test_time_limit_keeps_explicit_timeout() -> None:
    message = TimeLimitMiddleware(default_timeout_seconds=60).pre_execute(message=_make_message(labels={"timeout": 5}))

    assert message.labels["timeout"] == 5


def test_lifecycle_logs_start_and_success_with_duration(caplog: pytest.LogCaptureFixture) -> None:
    middleware = TaskLifecycleLogMiddleware()
    message = _make_message()

    with caplog.at_level(logging.INFO, logger="taskiq.lifecycle"):
        middleware.pre_execute(message=message)
        middleware.post_execute(message=message, result=_make_result(is_err=False))

    assert [record.getMessage() for record in caplog.records] == ["Task started", "Task succeeded"]
    assert caplog.records[1].duration_seconds is not None
    assert caplog.records[1].task_name == "demo.task"


def test_lifecycle_logs_failure_with_exception_info(caplog: pytest.LogCaptureFixture) -> None:
    middleware = TaskLifecycleLogMiddleware()
    message = _make_message()
    error = ValueError("boom")

    with caplog.at_level(logging.INFO, logger="taskiq.lifecycle"):
        middleware.pre_execute(message=message)
        middleware.post_execute(message=message, result=_make_result(is_err=True, error=error))

    failure = caplog.records[-1]
    assert failure.levelno == logging.ERROR
    assert failure.getMessage() == "Task failed"
    assert failure.exc_info is not None
    assert failure.exc_info[1] is error

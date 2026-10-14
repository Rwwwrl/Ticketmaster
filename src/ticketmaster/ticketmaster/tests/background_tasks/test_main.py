from libs.taskiq_ext import RequestIdMiddleware, TaskLifecycleLogMiddleware, TimeLimitMiddleware
from taskiq.middlewares import SmartRetryMiddleware
from ticketmaster.background_tasks.main import broker


def test_broker_middlewares_run_request_id_first() -> None:
    assert [type(middleware) for middleware in broker.middlewares] == [
        RequestIdMiddleware,
        TimeLimitMiddleware,
        SmartRetryMiddleware,
        TaskLifecycleLogMiddleware,
    ]

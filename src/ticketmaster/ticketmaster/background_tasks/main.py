from aio_pika import ExchangeType
from libs.aws.session import bind_task_role_to_aws_session
from libs.common.enums import AppNameEnum, ServiceNameEnum
from libs.logging import setup_logging
from libs.logging.enums import ProcessTypeEnum
from libs.sentry_ext import setup_sentry
from libs.sqlmodel_ext import ReadSession, SessionPrimary
from libs.taskiq_ext import RequestIdMiddleware, TaskLifecycleLogMiddleware, TimeLimitMiddleware
from taskiq import TaskiqEvents, TaskiqState, async_shared_broker
from taskiq.middlewares import SmartRetryMiddleware
from taskiq_aio_pika import AioPikaBroker, Exchange, Queue

from ticketmaster.settings import settings
from ticketmaster.utils import init_sqlmodel_engine

_MAX_ASYNC_TASKS = 10
_DEFAULT_TASK_TIMEOUT_SECONDS = 60

broker = AioPikaBroker(
    url=settings.rabbitmq_url,
    qos=_MAX_ASYNC_TASKS,
    # NOTE @sosov: The rabbitmq-topology Job declares these (src/rabbitmq_topology/resources.py); the worker only
    # checks passively that they exist, so the names must match.
    exchange=Exchange(name="default", type=ExchangeType.DIRECT, passive=True),
    task_queues=[Queue(name="default", passive=True)],
    dead_letter_queue=Queue(name="default.dead_letter", passive=True),
    delay_queue=Queue(name="default.delay", passive=True),
)
broker.add_middlewares(
    RequestIdMiddleware(),
    TimeLimitMiddleware(default_timeout_seconds=_DEFAULT_TASK_TIMEOUT_SECONDS),
    SmartRetryMiddleware(use_jitter=True),
    TaskLifecycleLogMiddleware(),
)
async_shared_broker.default_broker(broker)


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _on_worker_startup(state: TaskiqState) -> None:
    setup_logging(
        settings=settings,
        app_name=AppNameEnum.TICKETMASTER,
        service_name=ServiceNameEnum.TICKETMASTER,
        process_type=ProcessTypeEnum.TASKIQ_WORKER,
    )
    setup_sentry(settings=settings, release=settings.version)

    primary_engine = init_sqlmodel_engine(
        db_url=settings.postgres_pooler_db_url,
        application_name="ticketmaster-worker",
    )
    SessionPrimary.configure(bind=primary_engine)
    state.sqlmodel_primary_engine = primary_engine

    reader_engine = init_sqlmodel_engine(
        db_url=settings.postgres_pooler_ro_db_url,
        application_name="ticketmaster-worker",
    )
    ReadSession.configure(bind=reader_engine)
    state.sqlmodel_reader_engine = reader_engine

    if settings.aws_task_role is not None:
        bind_task_role_to_aws_session(
            region=settings.aws_task_role.region,
            access_key_id=settings.aws_task_role.access_key_id,
            secret_access_key=settings.aws_task_role.secret_access_key,
            session_token=settings.aws_task_role.session_token,
        )


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def _on_worker_shutdown(state: TaskiqState) -> None:
    await state.sqlmodel_primary_engine.dispose()
    await state.sqlmodel_reader_engine.dispose()

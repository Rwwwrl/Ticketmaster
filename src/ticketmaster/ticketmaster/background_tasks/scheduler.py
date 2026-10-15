from uuid import uuid4

from libs.common.enums import AppNameEnum, ServiceNameEnum
from libs.logging import setup_logging
from libs.logging.enums import ProcessTypeEnum
from libs.sentry_ext import setup_sentry
from taskiq import TaskiqEvents, TaskiqScheduler, async_shared_broker
from taskiq.schedule_sources import LabelScheduleSource
from taskiq.scheduler.scheduled_task import ScheduledTask

from ticketmaster.background_tasks.main import broker
from ticketmaster.settings import settings


class _MessageBodyScheduleSource(LabelScheduleSource):
    def pre_send(self, task: ScheduledTask) -> None:
        logical_id = uuid4()
        task.kwargs["body"] = {"logical_id": str(logical_id)}
        task.task_id = str(logical_id)


scheduler = TaskiqScheduler(broker=broker, sources=[_MessageBodyScheduleSource(async_shared_broker)])


@broker.on_event(TaskiqEvents.CLIENT_STARTUP)
async def _on_client_startup() -> None:
    setup_logging(
        settings=settings,
        app_name=AppNameEnum.TICKETMASTER,
        service_name=ServiceNameEnum.TICKETMASTER,
        process_type=ProcessTypeEnum.TASKIQ_SCHEDULER,
    )
    setup_sentry(settings=settings, release=settings.version)

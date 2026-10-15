import asyncio
import logging
import signal

from libs.common.enums import AppNameEnum, ServiceNameEnum
from libs.logging import setup_logging
from libs.logging.enums import ProcessTypeEnum
from libs.sentry_ext import setup_sentry
from libs.sqlmodel_ext import SessionPrimary
from libs.taskiq_ext.utils import build_task_registry

import ticketmaster.background_tasks.tasks  # noqa: F401
from ticketmaster.background_tasks import utils
from ticketmaster.background_tasks.main import broker
from ticketmaster.settings import settings
from ticketmaster.utils import init_sqlmodel_engine

_logger = logging.getLogger(__name__)

_BATCH_SIZE = 100
_PUBLISH_TIMEOUT_SECONDS = 10.0
_IDLE_SLEEP_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 30.0


async def main() -> None:
    setup_logging(
        settings=settings,
        app_name=AppNameEnum.TICKETMASTER,
        service_name=ServiceNameEnum.TICKETMASTER,
        process_type=ProcessTypeEnum.OUTBOX_RELAY,
    )
    setup_sentry(settings=settings, release=settings.version)

    engine = init_sqlmodel_engine(
        db_url=settings.postgres_pooler_db_url,
        application_name="ticketmaster-outbox-relay",
    )
    SessionPrimary.configure(bind=engine)

    await broker.startup()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signal_number, stop.set)

    try:
        tasks_by_code = build_task_registry(broker=broker)
        consecutive_failures = 0

        while not stop.is_set():
            try:
                acked = await utils.relay_batch(
                    broker=broker,
                    tasks_by_code=tasks_by_code,
                    batch_size=_BATCH_SIZE,
                    publish_timeout=_PUBLISH_TIMEOUT_SECONDS,
                )
            except Exception:
                consecutive_failures += 1
                _logger.exception("Outbox relay batch failed", extra={"consecutive_failures": consecutive_failures})
                backoff = min(_IDLE_SLEEP_SECONDS * 2**consecutive_failures, _MAX_BACKOFF_SECONDS)
                await utils.sleep_or_stop(stop=stop, seconds=backoff)
                continue

            consecutive_failures = 0
            if acked < _BATCH_SIZE:
                await utils.sleep_or_stop(stop=stop, seconds=_IDLE_SLEEP_SECONDS)
    finally:
        await broker.shutdown()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

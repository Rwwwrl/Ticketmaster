import asyncio
import logging
from contextlib import suppress
from typing import Any

from libs.sqlmodel_ext import SessionPrimary
from libs.taskiq_ext.utils import TasksByCode
from sqlalchemy import text
from taskiq import AsyncBroker
from taskiq.decor import AsyncTaskiqDecoratedTask

from ticketmaster.repositories import OutboxRepository
from ticketmaster.schemas.dtos import OutboxMessageDTO

_logger = logging.getLogger(__name__)


async def _publish(
    broker: AsyncBroker,
    task: AsyncTaskiqDecoratedTask[Any, Any],
    outbox_message: OutboxMessageDTO,
) -> OutboxMessageDTO:
    try:
        kicker = task.kicker().with_broker(broker=broker).with_task_id(task_id=outbox_message.message["logical_id"])
        await kicker.kiq(body=outbox_message.message)
    except Exception:
        _logger.exception(
            "Outbox publish failed",
            extra={"outbox_id": outbox_message.id, "code": outbox_message.code},
        )
        raise

    return outbox_message


async def relay_batch(
    broker: AsyncBroker,
    tasks_by_code: TasksByCode,
    batch_size: int,
    publish_timeout: float,
) -> int:
    async with SessionPrimary() as session, session.begin():
        await session.exec(text("SET LOCAL idle_in_transaction_session_timeout = '30s'"))

        outbox_messages = await OutboxRepository.lock_batch(session=session, limit=batch_size)
        if not outbox_messages:
            return 0

        publishes: list[asyncio.Task[OutboxMessageDTO]] = []
        for outbox_message in outbox_messages:
            task = tasks_by_code.get(outbox_message.code)
            if task is None:
                _logger.error(
                    "Outbox message has no task for its code",
                    extra={"outbox_id": outbox_message.id, "code": outbox_message.code},
                )
                continue

            publishes.append(asyncio.create_task(_publish(broker=broker, task=task, outbox_message=outbox_message)))

        if not publishes:
            return 0

        done, pending = await asyncio.wait(publishes, timeout=publish_timeout)
        for publish in pending:
            publish.cancel()

        if pending:
            _logger.warning(
                "Outbox publish timed out",
                extra={"timed_out": len(pending), "locked": len(outbox_messages), "timeout_seconds": publish_timeout},
            )
            await asyncio.gather(*pending, return_exceptions=True)

        acked_ids = [publish.result().id for publish in done if publish.exception() is None]
        await OutboxRepository.delete_by_ids(session=session, ids=acked_ids)

    return len(acked_ids)


async def sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    with suppress(TimeoutError):
        async with asyncio.timeout(seconds):
            await stop.wait()

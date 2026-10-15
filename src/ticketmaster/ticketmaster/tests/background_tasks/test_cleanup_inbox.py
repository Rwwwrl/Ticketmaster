from uuid import uuid4

import pytest
from libs.sqlmodel_ext import SessionPrimary
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from taskiq import InMemoryBroker
from taskiq.scheduler.scheduled_task import ScheduledTask
from ticketmaster.background_tasks.scheduler import scheduler
from ticketmaster.background_tasks.tasks import cleanup_inbox
from ticketmaster.models import InboxMessage
from ticketmaster.schemas.task_messages import CleanupInboxTaskMessage


@pytest.mark.asyncio(loop_scope="session")
async def test_cleanup_inbox_deletes_expired_rows_across_batches(
    taskiq_broker: InMemoryBroker,
    sqlmodel_primary_engine: AsyncEngine,
) -> None:
    async with SessionPrimary() as session, session.begin():
        await session.exec(
            text(
                "INSERT INTO inbox_message (code, logical_id, created_at, updated_at) "
                "SELECT 100, gen_random_uuid(), now() - interval '15 days', now() FROM generate_series(1, 10001)"
            )
        )
        await session.exec(
            text("INSERT INTO inbox_message (code, logical_id) VALUES (100, :logical_id)").bindparams(
                logical_id=uuid4()
            )
        )

    result = await (await cleanup_inbox.kiq(body=CleanupInboxTaskMessage(logical_id=uuid4()))).wait_result()

    assert not result.is_err
    async with SessionPrimary() as session, session.begin():
        assert len((await session.exec(select(InboxMessage))).all()) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_scheduler_source_generates_a_fresh_message_body_for_every_send() -> None:
    source = scheduler.sources[0]
    await source.startup()
    task = next(task for task in await source.get_schedules() if task.task_name == "cleanup_inbox")

    bodies = []
    for _ in range(2):
        source.pre_send(task)
        bodies.append(CleanupInboxTaskMessage.model_validate(task.kwargs["body"]))
        assert task.task_id == str(bodies[-1].logical_id)

    assert bodies[0].logical_id != bodies[1].logical_id
    assert isinstance(task, ScheduledTask)

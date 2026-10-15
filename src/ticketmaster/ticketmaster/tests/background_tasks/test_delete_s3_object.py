from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from libs.sqlmodel_ext import SessionPrimary
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from taskiq import InMemoryBroker
from ticketmaster.background_tasks.tasks import delete_s3_object
from ticketmaster.models import InboxMessage
from ticketmaster.schemas.task_messages import DeleteS3ObjectTaskMessage


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_s3_object_deletes_the_object(
    taskiq_broker: InMemoryBroker, mock_s3: AsyncMock, sqlmodel_primary_engine: AsyncEngine
) -> None:
    message = DeleteS3ObjectTaskMessage(logical_id=uuid4(), bucket="media-bucket", key="trailers/1.mp4")

    result = await (await delete_s3_object.kiq(body=message)).wait_result()

    assert not result.is_err
    mock_s3.delete_object.assert_awaited_once_with(Bucket="media-bucket", Key="trailers/1.mp4")


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_s3_object_duplicate_runs_side_effect_once(
    taskiq_broker: InMemoryBroker, mock_s3: AsyncMock, sqlmodel_primary_engine: AsyncEngine
) -> None:
    message = DeleteS3ObjectTaskMessage(logical_id=uuid4(), bucket="media-bucket", key="trailers/1.mp4")

    await (await delete_s3_object.kiq(body=message)).wait_result()
    result = await (await delete_s3_object.kiq(body=message)).wait_result()

    assert not result.is_err
    mock_s3.delete_object.assert_awaited_once()
    async with SessionPrimary() as session, session.begin():
        assert len((await session.exec(select(InboxMessage))).all()) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_s3_object_failure_leaves_no_inbox_row(
    taskiq_broker: InMemoryBroker, mock_s3: AsyncMock, sqlmodel_primary_engine: AsyncEngine
) -> None:
    mock_s3.delete_object.side_effect = RuntimeError("boom")
    message = DeleteS3ObjectTaskMessage(logical_id=uuid4(), bucket="media-bucket", key="trailers/1.mp4")

    result = await (await delete_s3_object.kiq(body=message)).wait_result()

    assert result.is_err
    async with SessionPrimary() as session, session.begin():
        assert (await session.exec(select(InboxMessage))).all() == []

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from libs.sqlmodel_ext import SessionPrimary
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from taskiq import InMemoryBroker
from ticketmaster.background_tasks.tasks import delete_cognito_user
from ticketmaster.models import InboxMessage
from ticketmaster.schemas.task_messages import DeleteCognitoUserTaskMessage


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_cognito_user_deletes_the_user(
    taskiq_broker: InMemoryBroker, mock_cognito: AsyncMock, sqlmodel_primary_engine: AsyncEngine
) -> None:
    message = DeleteCognitoUserTaskMessage(logical_id=uuid4(), pool_id="pool-1", cognito_username="user-1")

    result = await (await delete_cognito_user.kiq(body=message)).wait_result()

    assert not result.is_err
    mock_cognito.admin_delete_user.assert_awaited_once_with(UserPoolId="pool-1", Username="user-1")


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_cognito_user_when_user_not_found_succeeds(
    taskiq_broker: InMemoryBroker, mock_cognito: AsyncMock, sqlmodel_primary_engine: AsyncEngine
) -> None:
    mock_cognito.admin_delete_user.side_effect = mock_cognito.exceptions.UserNotFoundException()
    message = DeleteCognitoUserTaskMessage(logical_id=uuid4(), pool_id="pool-1", cognito_username="gone")

    result = await (await delete_cognito_user.kiq(body=message)).wait_result()

    assert not result.is_err


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_cognito_user_duplicate_runs_side_effect_once(
    taskiq_broker: InMemoryBroker, mock_cognito: AsyncMock, sqlmodel_primary_engine: AsyncEngine
) -> None:
    message = DeleteCognitoUserTaskMessage(logical_id=uuid4(), pool_id="pool-1", cognito_username="user-1")

    await (await delete_cognito_user.kiq(body=message)).wait_result()
    result = await (await delete_cognito_user.kiq(body=message)).wait_result()

    assert not result.is_err
    mock_cognito.admin_delete_user.assert_awaited_once()
    async with SessionPrimary() as session, session.begin():
        assert len((await session.exec(select(InboxMessage))).all()) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_cognito_user_failure_leaves_no_inbox_row(
    taskiq_broker: InMemoryBroker, mock_cognito: AsyncMock, sqlmodel_primary_engine: AsyncEngine
) -> None:
    mock_cognito.admin_delete_user.side_effect = RuntimeError("boom")
    message = DeleteCognitoUserTaskMessage(logical_id=uuid4(), pool_id="pool-1", cognito_username="user-1")

    result = await (await delete_cognito_user.kiq(body=message)).wait_result()

    assert result.is_err
    async with SessionPrimary() as session, session.begin():
        assert (await session.exec(select(InboxMessage))).all() == []

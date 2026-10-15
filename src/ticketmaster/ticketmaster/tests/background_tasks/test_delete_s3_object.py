from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from taskiq import InMemoryBroker
from ticketmaster.background_tasks.tasks import delete_s3_object
from ticketmaster.schemas.task_messages import DeleteS3ObjectTaskMessage


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_s3_object_deletes_the_object(taskiq_broker: InMemoryBroker, mock_s3: AsyncMock) -> None:
    message = DeleteS3ObjectTaskMessage(logical_id=uuid4(), bucket="media-bucket", key="trailers/1.mp4")

    result = await (await delete_s3_object.kiq(body=message)).wait_result()

    assert not result.is_err
    mock_s3.delete_object.assert_awaited_once_with(Bucket="media-bucket", Key="trailers/1.mp4")

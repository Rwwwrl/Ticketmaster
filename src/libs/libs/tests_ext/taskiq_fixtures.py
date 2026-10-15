from collections.abc import AsyncGenerator

import pytest_asyncio
from taskiq import InMemoryBroker, async_shared_broker


@pytest_asyncio.fixture(scope="session")
async def taskiq_broker() -> AsyncGenerator[InMemoryBroker]:
    broker = InMemoryBroker()
    async_shared_broker.default_broker(broker)
    await broker.startup()
    yield broker
    await broker.shutdown()

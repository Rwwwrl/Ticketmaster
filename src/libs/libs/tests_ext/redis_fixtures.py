from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from libs.redis_ext import redis_proxy
from libs.redis_ext.settings import RedisSettingsMixin

_TEST_REDIS_DB = 15


@pytest_asyncio.fixture(scope="session")
async def redis(settings: RedisSettingsMixin) -> AsyncGenerator[Redis]:
    client = Redis.from_url(url=settings.redis_url, decode_responses=False, db=_TEST_REDIS_DB)
    await client.flushdb()
    redis_proxy.configure_with_client(client=client)

    yield client

    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture(autouse=True)
async def _clear_redis(request: pytest.FixtureRequest) -> AsyncGenerator[None]:
    yield

    if redis.__name__ not in request.fixturenames:
        return

    client: Redis = request.getfixturevalue("redis")
    await client.flushdb()

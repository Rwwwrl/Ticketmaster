import asyncio
import os
from collections.abc import AsyncGenerator
from dataclasses import replace

import pytest
import pytest_asyncio
from aio_pika import connect
from aiormq.exceptions import ChannelNotFoundEntity
from rabbitmq_topology.apply import apply_topology
from rabbitmq_topology.resources import (
    DEAD_LETTER_QUEUES,
    DEFAULT_DEAD_LETTER_QUEUE,
    DEFAULT_DELAY_QUEUE,
    DEFAULT_EXCHANGE,
    DEFAULT_QUEUE,
    DELAY_QUEUES,
    EXCHANGES,
    QUEUES,
)
from taskiq.kicker import AsyncKicker
from taskiq_aio_pika import AioPikaBroker


def _build_broker(url: str, passive: bool) -> AioPikaBroker:
    return AioPikaBroker(
        url=url,
        exchange=replace(DEFAULT_EXCHANGE, passive=passive),
        task_queues=[replace(DEFAULT_QUEUE, passive=passive)],
        dead_letter_queue=replace(DEFAULT_DEAD_LETTER_QUEUE, passive=passive),
        delay_queue=replace(DEFAULT_DELAY_QUEUE, passive=passive),
    )


@pytest.fixture(scope="session")
def rabbitmq_url() -> str:
    return os.environ["RABBITMQ_URL"]


async def _delete_topology(url: str) -> None:
    connection = await connect(url)
    try:
        channel = await connection.channel()
        for queue in [*DEAD_LETTER_QUEUES, *QUEUES, *DELAY_QUEUES]:
            await channel.queue_delete(queue_name=queue.name)
        for exchange in EXCHANGES:
            await channel.exchange_delete(exchange_name=exchange.name)
    finally:
        await connection.close()


@pytest_asyncio.fixture(autouse=True)
async def _clean_topology(rabbitmq_url: str) -> AsyncGenerator[None]:
    await _delete_topology(url=rabbitmq_url)
    yield
    # NOTE @sosov: Leave the topology declared, because local dev shares this RabbitMQ with `just runworker`.
    await apply_topology(amqp_url=rabbitmq_url)


@pytest.mark.asyncio(loop_scope="session")
async def test_apply_twice_is_a_noop(rabbitmq_url: str) -> None:
    await apply_topology(amqp_url=rabbitmq_url)
    await apply_topology(amqp_url=rabbitmq_url)


@pytest.mark.asyncio(loop_scope="session")
async def test_resources_match_the_arguments_taskiq_derives(rabbitmq_url: str) -> None:
    await apply_topology(amqp_url=rabbitmq_url)
    broker = _build_broker(url=rabbitmq_url, passive=False)

    # NOTE @sosov: A non-passive re-declare with different arguments fails with PRECONDITION_FAILED.
    await broker.startup()
    await broker.shutdown()


@pytest.mark.asyncio(loop_scope="session")
async def test_passive_broker_starts_after_apply(rabbitmq_url: str) -> None:
    await apply_topology(amqp_url=rabbitmq_url)
    broker = _build_broker(url=rabbitmq_url, passive=True)

    await broker.startup()
    await broker.shutdown()


@pytest.mark.asyncio(loop_scope="session")
async def test_passive_broker_fails_when_topology_is_missing(rabbitmq_url: str) -> None:
    broker = _build_broker(url=rabbitmq_url, passive=True)

    with pytest.raises(ChannelNotFoundEntity):
        await broker.startup()
    await broker.shutdown()


@pytest.mark.asyncio(loop_scope="session")
async def test_kicked_message_lands_in_work_queue(rabbitmq_url: str) -> None:
    await apply_topology(amqp_url=rabbitmq_url)
    broker = _build_broker(url=rabbitmq_url, passive=True)
    await broker.startup()

    await AsyncKicker(task_name="demo.task", broker=broker, labels={}).with_task_id("task-1").kiq()
    await broker.shutdown()

    connection = await connect(rabbitmq_url)
    try:
        channel = await connection.channel()
        queue = await channel.get_queue(name=DEFAULT_QUEUE.name)
        message = await queue.get(timeout=5)
        assert message.headers["task_id"] == "task-1"
        await message.ack()
        for queue in (DEFAULT_DEAD_LETTER_QUEUE, DEFAULT_DELAY_QUEUE):
            assert (await channel.get_queue(name=queue.name)).declaration_result.message_count == 0
    finally:
        await connection.close()


@pytest.mark.asyncio(loop_scope="session")
async def test_delayed_message_returns_to_work_queue(rabbitmq_url: str) -> None:
    await apply_topology(amqp_url=rabbitmq_url)
    broker = _build_broker(url=rabbitmq_url, passive=True)
    await broker.startup()

    await (
        AsyncKicker(task_name="demo.task", broker=broker, labels={}).with_task_id("task-2").with_labels(delay=0.5).kiq()
    )
    await broker.shutdown()

    connection = await connect(rabbitmq_url)
    try:
        channel = await connection.channel()
        queue = await channel.get_queue(name=DEFAULT_QUEUE.name)
        # NOTE @sosov: `Queue.get` returns immediately, so poll until the delay expires and the message is dead-lettered.
        message = None
        for _ in range(40):
            message = await queue.get(fail=False)
            if message is not None:
                break
            await asyncio.sleep(0.25)
        assert message is not None
        assert message.headers["task_id"] == "task-2"
        await message.ack()
    finally:
        await connection.close()

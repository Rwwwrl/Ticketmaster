import asyncio
import os

from aio_pika import connect
from aio_pika.abc import AbstractExchange, AbstractQueue

from rabbitmq_topology.resources import BINDINGS, DEAD_LETTER_QUEUES, DELAY_QUEUES, EXCHANGES, QUEUES


async def apply_topology(amqp_url: str) -> None:
    connection = await connect(amqp_url)

    try:
        channel = await connection.channel()

        declared_exchanges: dict[str, AbstractExchange] = {}
        for exchange in EXCHANGES:
            declared_exchanges[exchange.name] = await channel.declare_exchange(
                name=exchange.name,
                type=exchange.type,
                durable=exchange.durable,
                arguments=exchange.arguments,
            )

        declared_queues: dict[str, AbstractQueue] = {}
        for queue in [*DEAD_LETTER_QUEUES, *QUEUES, *DELAY_QUEUES]:
            declared_queues[queue.name] = await channel.declare_queue(
                name=queue.name,
                durable=queue.durable,
                arguments={"x-queue-type": queue.type.value, **queue.arguments},
            )

        for binding in BINDINGS:
            for queue in binding.queues:
                await declared_queues[queue.name].bind(
                    exchange=declared_exchanges[binding.exchange.name],
                    routing_key=queue.routing_key or queue.name,
                )
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(apply_topology(amqp_url=os.environ["RABBITMQ_URL"]))

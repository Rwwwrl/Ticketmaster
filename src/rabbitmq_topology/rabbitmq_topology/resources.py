from aio_pika import ExchangeType
from taskiq_aio_pika import Exchange, Queue, QueueType

from rabbitmq_topology.schemas.dtos import RabbitMQBinding

DEFAULT_EXCHANGE = Exchange(
    name="default",
    type=ExchangeType.DIRECT,
    durable=True,
)

EXCHANGES: list[Exchange] = [
    DEFAULT_EXCHANGE,
]

DEFAULT_DEAD_LETTER_QUEUE = Queue(
    name="default.dead_letter",
    type=QueueType.QUORUM,
    durable=True,
)

DEAD_LETTER_QUEUES: list[Queue] = [
    DEFAULT_DEAD_LETTER_QUEUE,
]

DEFAULT_QUEUE = Queue(
    name="default",
    type=QueueType.QUORUM,
    durable=True,
    arguments={
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": DEFAULT_DEAD_LETTER_QUEUE.name,
    },
)

QUEUES: list[Queue] = [
    DEFAULT_QUEUE,
]

DEFAULT_DELAY_QUEUE = Queue(
    name=f"{DEFAULT_QUEUE.name}.delay",
    type=QueueType.QUORUM,
    durable=True,
    arguments={
        "x-dead-letter-exchange": DEFAULT_EXCHANGE.name,
        "x-dead-letter-routing-key": DEFAULT_QUEUE.name,
    },
)

DELAY_QUEUES: list[Queue] = [
    DEFAULT_DELAY_QUEUE,
]

BINDINGS: list[RabbitMQBinding] = [
    RabbitMQBinding(
        exchange=DEFAULT_EXCHANGE,
        queues=[DEFAULT_QUEUE],
    ),
]

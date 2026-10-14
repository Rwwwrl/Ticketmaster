from pydantic import BaseModel, ConfigDict, InstanceOf
from taskiq_aio_pika import Exchange, Queue


class RabbitMQBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange: InstanceOf[Exchange]
    queues: list[InstanceOf[Queue]]

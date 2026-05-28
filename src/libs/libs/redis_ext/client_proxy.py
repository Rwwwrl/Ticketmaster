from redis.asyncio import Redis


class _RedisClientProxy:
    def __init__(self) -> None:
        self.redis: Redis | None = None

    def configure_with_client(self, client: Redis) -> None:
        self.redis = client


redis_proxy = _RedisClientProxy()

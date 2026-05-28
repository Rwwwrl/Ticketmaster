from libs.redis_ext.client_proxy import redis_proxy


async def health_check() -> None:
    await redis_proxy.redis.ping()

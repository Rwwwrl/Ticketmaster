import asyncio

from cryptography.hazmat.primitives import serialization

from libs.aws.session import aws_session


class KMSPublicKeyCache:
    def __init__(self, key_arn: str) -> None:
        self._key_arn = key_arn
        self._cached_pem: bytes | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> bytes:
        # NOTE @sosov: double-checked locking. Fast path takes no lock — steady-state
        # every request hits the cache. The lock only matters during cold-start surge:
        # without it N concurrent first requests fire N parallel `kms:GetPublicKey`
        # calls which can hit the per-account KMS rate limit.
        if self._cached_pem is not None:
            return self._cached_pem

        async with self._lock:
            if self._cached_pem is None:
                self._cached_pem = await self._fetch_from_kms()
            return self._cached_pem

    async def get_force_refreshed(self) -> bytes:
        async with self._lock:
            self._cached_pem = await self._fetch_from_kms()
            return self._cached_pem

    async def _fetch_from_kms(self) -> bytes:
        async with aws_session.client(service_name="kms") as kms:
            response = await kms.get_public_key(KeyId=self._key_arn)

        public_key = serialization.load_der_public_key(data=response["PublicKey"])

        return public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

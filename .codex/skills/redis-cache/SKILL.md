---
name: redis-cache
description: Apply Ticketmaster's Redis caching conventions. Use for Redis connectivity, typed cache documents, cache keys, TTLs, cache-aside services, bulk caching, page or service caching, invalidation, versioning, and Redis tests.
---

# Ticketmaster Redis Cache

Treat Redis as an optional optimization. PostgreSQL remains the source of truth and Redis outages must not break core behavior.

## Place Cache Code

- Keep reusable primitives, settings, proxy behavior, and test fixtures in `src/libs/libs/redis_ext/`.
- Keep service cache documents, service-cache payloads, repositories, keys, and TTL constants in `src/ticketmaster/ticketmaster/redis_cache/`.
- Keep service-cache namespace rotation alongside the code that owns the mutation. It currently lives in `ticketmaster/admin/redis_cache/` only because all current create and update operations are admin operations; the admin location is not an architectural requirement.
- Keep cache-aside orchestration in the service layer, not routes or database repositories.

Configure one async client during FastAPI lifespan with `Redis.from_url(..., decode_responses=False)`, expose it through `redis_proxy`, close it on shutdown, and retain Redis in readiness checks.

## Cache Typed Entity Documents

1. Subclass `BaseCacheDocument`.
2. Declare every persisted field explicitly.
3. Add DTO-to-document and document-to-DTO mappings.
4. Serialize with `model_dump_json()`.
5. Deserialize only with `from_raw_cache()`, which converts Pydantic failures to `FromRawCacheValidationError`.
6. Require the application version explicitly in every entity-cache repository read and write method.
7. Pass `settings.version`, sourced from the application's `pyproject.toml`, from the service layer.
8. Include that version in every key, such as `event:v0.15.0:42`.

Do not declare versions on cache-document classes. Application package versions isolate every deployment's entity keys, preventing incompatible payloads from colliding during rolling deployments. Old application-version generations expire through their finite TTL.

Use finite TTLs from `redis_cache/consts.py`; entity and service caches currently use 300 seconds.

## Implement Cache-Aside Behavior

On reads:

1. Attempt the cache lookup.
2. Treat a missing key, malformed document, or `RedisError` as a cache miss.
3. Read from PostgreSQL.
4. Best-effort warm Redis.
5. Return the database-backed DTO.

Suppress only the expected Redis, cache-miss, and cache-validation exceptions around cache operations. Never suppress database or domain failures.

For bulk entity reads:

- Return early for an empty ID list.
- Use `mget`.
- Skip missing or malformed documents.
- Fetch only missing IDs from PostgreSQL.
- Batch writes through a non-transactional pipeline.
- Reconstruct the final list in the requested ID order; neither Redis nor SQL result order is authoritative.

Raise a domain-specific cache-not-found exception for a missing single document.

## Cache Service Results

Subclass `BaseServiceCache` for typed service payloads. Include every behavior-affecting input in the key:

- service name
- application version
- invalidation namespace
- cursor
- sort key
- page size

Cache compact entity IDs and the next cursor, then hydrate entity documents separately. Limit page caching to the hot bounded window; event listing currently caches page indexes 0 through 4.

Treat a missing namespace key explicitly as a cache miss or initialize it safely. Do not call `.decode()` on a possible `None` value.

## Invalidate Safely

- Rotate the persistent service-cache namespace when a mutation changes list membership, order, or rendered list data.
- Do not delete entity-cache documents on mutation. Entity freshness currently relies exclusively on the 300-second TTL.
- Accept that a newly rotated service-cache result may hydrate an entity document written before the mutation until that document expires.
- Let every application-version generation expire by TTL. Never scan or flush the entire Redis database.

Service namespace rotation is best effort and currently occurs before the outer database transaction commits. Treat this as a known consistency limitation; do not describe it as atomic post-commit invalidation.

## Test Cache Semantics

Use the shared async Redis fixture, which isolates test DB 15 and flushes state around Redis tests. Cover:

- complete and version-isolated keys
- TTLs and JSON round trips
- missing and malformed payloads
- explicit application-version injection
- partial bulk misses, backfill, and output order
- service-key input isolation
- service namespace rotation on mutations
- entity documents remaining cached after mutations until TTL expiration
- page-cache bounds
- Redis read and write failures falling through to PostgreSQL

Run:

```bash
just up-infra
poetry run pytest src/ticketmaster/ticketmaster/tests/redis_cache src/ticketmaster/ticketmaster/tests/services -s
poetry run ruff check .
poetry run ruff format --check .
```

Bump `src/libs` or `src/ticketmaster` package versions when their source changes; pull-request CI enforces it.

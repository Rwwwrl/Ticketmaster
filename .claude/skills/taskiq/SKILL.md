---
name: taskiq
description: Apply Ticketmaster's background-task conventions. Use for TaskIQ tasks, the broker and worker, RabbitMQ topology (exchange, queues, dead-letter, delay), task middlewares, retries, worker CLI flags and grace periods, and testing tasks with the in-memory broker.
---

# Ticketmaster Background Tasks

Background tasks run on TaskIQ over RabbitMQ (`taskiq-aio-pika` 0.6.x, whose API is `Exchange`/`Queue` dataclasses; the 0.5 `exchange_name=`/`queue_name=` API is gone). Deployment details (StatefulSet, Job, secrets, waves) are in the `deployment` skill, "Run RabbitMQ".

## Layout

- `libs/taskiq_ext/`: `settings.py` (`TaskIQSettingsMixin`, one field `rabbitmq_url`), `middlewares.py`, and the schema-free outbox pieces: `schemas/task_messages.py` (`BaseTaskMessage`) and `utils.py` (`build_task_registry`). The `outbox_message` table, `OutboxMessageDTO`, `OutboxRepository` and the relay are service code: each service owns its outbox table and migration (`ticketmaster/models.py`, `schemas/dtos.py`, `repositories.py`), because libs must not ship tables into a service's metadata.
- `ticketmaster/background_tasks/main.py`: the `broker`, middlewares and the `WORKER_STARTUP` / `WORKER_SHUTDOWN` hooks. `tasks.py`: task definitions; the worker CLI imports it. `utils.py`: `relay_batch` (one locked batch) and `sleep_or_stop`. `outbox_relay.py`: the relay process entry point, which owns the polling loop, the backoff and the SIGTERM/SIGINT stop event.
- `ticketmaster/schemas/task_messages.py`: the concrete task messages (`DeleteS3ObjectTaskMessage` code `100`, `DeleteCognitoUserTaskMessage` code `101`).
- `src/rabbitmq_topology/`: its own project and image, used only by the topology Job. `resources.py` declares every exchange, queue and binding as module-level taskiq-aio-pika `Exchange`/`Queue` objects grouped into `EXCHANGES`, `DEAD_LETTER_QUEUES`, `QUEUES`, `DELAY_QUEUES` and `BINDINGS` (`schemas.RabbitMQBinding`); `apply.py` is the Job's entry point. Nothing else depends on it.
- Do not add settings named `rabbitmq_port` or `rabbitmq_service_host`: the Kubernetes Service `rabbitmq` injects `RABBITMQ_PORT` / `RABBITMQ_SERVICE_HOST` into pods that keep service links on.

## Rules

- **Register tasks on `taskiq.async_shared_broker`, never on the concrete broker.** `main.py` points it at the real broker with `async_shared_broker.default_broker(broker)`; tests swap in an `InMemoryBroker`. The HTTP process never starts a broker.
- **The Job owns the topology.** Add a resource to `rabbitmq_topology/resources.py` and to its group list; the Job declares every group in order (exchanges, dead-letter queues, queues, delay queues, bindings) with plain aio-pika, because taskiq-aio-pika has no API to declare a single resource. The worker's broker (`background_tasks/main.py`) refers to the same names with `passive=True`, so it only checks they exist and fails fast with `ChannelNotFoundEntity` when one is missing; keep the names in sync by hand. Explicit `arguments` in `resources.py` must equal what taskiq-aio-pika derives; a test re-declares them non-passively through the broker to prove it.
- **Queues are quorum.** Never set `max_priority` / `x-max-priority` (RabbitMQ rejects it on quorum queues). Queue arguments are immutable: changing one needs a policy or a manual queue delete (see the deployment skill).
- **Topology:** exchange `default` (direct) → queue `default` (routing key `default`). `default.dead_letter` collects poison messages over the quorum delivery limit; `default.delay` holds retry delays and dead-letters back into `tasks`. The two auxiliary queues are required by taskiq-aio-pika. Task messages only flow through `default`.
- **ACK after execution** (taskiq default). Broker redelivery happens only when a worker dies mid-task, so tasks must be idempotent.
- **Retries are opt-in per task:** `SmartRetryMiddleware(use_jitter=True)` retries only tasks labelled `retry_on_error=True` (3 attempts, 5 s constant delay). Keep the delay constant: a per-message TTL only expires at the head of the queue, so one long delay would block shorter ones behind it. After the last retry the message is gone (ack'd); only the ERROR log and Sentry event remain.
- **Middleware order is significant:** `RequestIdMiddleware` first (restores `request_id_var` from the `request_id` label before anything logs), then `TimeLimitMiddleware` (default 60 s, sets the `timeout` label in `pre_execute` when the message has none), `SmartRetryMiddleware`, `TaskLifecycleLogMiddleware` (start/success/failure with duration; failures log `exc_info` so Sentry captures the stack).
- **Startup hooks:** only `WORKER_STARTUP` fires in a worker (it runs before the AMQP connection exists, so it must not use the broker). Processes that only publish fire `CLIENT_STARTUP`. Set up logging (`ProcessTypeEnum.TASKIQ_WORKER`), Sentry, the AWS task role and **both** engines there: `SessionPrimary` (pooler) and `ReadSession` (read-only pooler, `ticketmaster-worker` application name). A task picks the session by need: `SessionPrimary` for writes and anything that must read its own writes, `ReadSession` for stale-tolerant reads. Redis stays unbound until a task needs it.

## Outbox

A side effect that must follow a DB commit (an S3 or Cognito call, a cache purge) is never done inline and never `.kiq()`-ed from a route: write an outbox row in the same transaction, and the relay publishes it after commit.

- **Messages.** Subclass `BaseTaskMessage` (frozen, `logical_id: UUID`, `created_at`) in `ticketmaster/schemas/task_messages.py` with a unique `code: ClassVar[int]`; a missing or duplicate code fails at import. A dump always carries `code`; a load ignores it.
- **Tasks take exactly one parameter, `body: <Message>`, and there is one task per message type.** The relay maps `code → task` from that annotation (`build_task_registry`); two tasks for one message, or a task without that parameter, fail the relay at startup.
- **Producing.** Inside the open transaction: `await OutboxRepository.add(session=session, message=Msg(logical_id=request_id_var.get(), ...))`; in a request the request id is the `logical_id`, and one request must not emit two messages with the same `code` (the inbox key is `(logical_id, code)`). Snapshot every value the task needs into the message, because the rows it came from may be gone. The row holds only `code` and the JSON `message`; the relay publishes with `task_id = logical_id`, which the worker logs, so HTTP and worker logs correlate. `RequestIdMiddleware` guarantees the request id is a UUID (a non-UUID `X-Request-ID` is a 400).
- **Schema evolution.** A new field must have a default, because pending rows and old messages must still validate on a new worker. Never remove or retype a field in place; add a new message with a new code.
- **Drain before removing a task.** A row whose code has no task stays in the table and is logged at ERROR every round; stop producing the message in one deploy and remove the task in a later one.
- **Relay** (`ticketmaster-outbox-relay`, 2 replicas, `just runrelay` locally). Each round is one `SessionPrimary` transaction: `SELECT … ORDER BY id LIMIT 100 FOR UPDATE SKIP LOCKED`, publish the batch as concurrent tasks under `asyncio.wait(timeout=10)`, then one `DELETE … = ANY(ids)` for the acked rows. No semaphore: the batch size is the in-flight bound. Each publish just raises on failure, and `relay_batch` acks the tasks that finished without an exception and cancels the ones still pending at the deadline; a `TaskGroup` would cancel the healthy siblings on the first failure. SKIP LOCKED is what lets the replicas share the table and cover for each other.
- **Unroutable messages are not guarded.** If the `default` → `default` binding (or the queue) is removed by hand while the relay runs, RabbitMQ acks the publish, the stock `AioPikaBroker` ignores the returned message, and the relay deletes the row. Never remove the binding by hand; every process start re-asserts it. The fix, if it ever bites, is to reopen the write channel with `on_return_raises=True`.
- **No ordering, at least once.** Tasks must tolerate duplicates and reordering. No probes: a dead process is restarted by the kubelet, and the relay serves no traffic.

## Worker CLI

```
poetry run taskiq worker ticketmaster.background_tasks.main:broker ticketmaster.background_tasks.tasks \
  --workers 1 --max-async-tasks 10 --wait-tasks-timeout 65 --shutdown-timeout 10 --no-configure-logging
```

- `--workers 1`: scale with replicas; the default of 2 processes doubles memory.
- `qos` (AMQP prefetch) equals `--max-async-tasks` (`_MAX_ASYNC_TASKS` in `main.py`).
- `--no-configure-logging`: our `setup_logging` owns logging.
- `terminationGracePeriodSeconds` must exceed `--wait-tasks-timeout` + `--shutdown-timeout` (65 + 10 → 90).

## Local development

- `just up-infra` starts RabbitMQ (AMQP on host port `15672`, management UI on `25672`, per the repo's "+10000" convention). `just rabbitmq-topology` declares the topology, `just runworker` starts a worker.
- `env.dev.yaml` (gitignored): `rabbitmq_url: amqp://ticketmaster:ticketmaster@localhost:15672/ticketmaster`.

## Testing

- Unit-test middlewares by calling hooks directly with a `TaskiqMessage` / `TaskiqResult` (see `libs/tests/taskiq_ext/test_middlewares.py`).
- The `taskiq_broker` session fixture (`libs.tests_ext.taskiq_fixtures`, loaded via root `addopts`) installs an `InMemoryBroker` as the shared broker's default; use it to run tasks without RabbitMQ.
- `rabbitmq_topology` tests run against a real RabbitMQ (docker compose locally, a service container in CI; the deployed broker is managed) and re-apply the topology on teardown.
- Run pytest from the repo root. Under `src/ticketmaster` the nested pytest config shadows the root `env` block; when the paths are all under `src/ticketmaster`, pass `-c pyproject.toml`.
- Outbox tests: the producers are covered by the delete-event and delete-me route tests, and the tasks by their own task tests. `BaseTaskMessage`, `build_task_registry`, `relay_batch` and the relay loop have no dedicated tests; the relay is checked on test-eu. The shared `mock_s3` / `mock_cognito` fixtures live in `ticketmaster/tests/conftest.py`; tasks run through the `taskiq_broker` fixture.

---
name: deployment
description: Work safely with Ticketmaster deployment and AWS infrastructure. Use for test releases, GitHub Actions, ECR, CodeArtifact, Helm template, rendered manifests, Argo CD, GitOps sync, EKS, kubectl, CloudFormation, Lambda, SSM, Secrets Manager, IAM, KMS, deployment diagnosis, or teardown.
---

# Ticketmaster Deployment

Use the repository workflows and templates as the source of truth. The only environment is `test-eu` in `eu-central-1`; never infer or invent production infrastructure.

Delivery to the cluster is GitOps: **Argo CD is the only writer to the cluster**, and git is the only source of truth for what it writes. CI never touches Kubernetes. `ticketmaster`, `frontend`, and the Cognito PreSignUp Lambda are deployed today. The shared ALB Ingress dispatches by path prefix — `/api/*` → `ticketmaster` (which mounts all routes under `/api`: `/api/v1`, `/api/admin`, docs at `/api/docs`), everything else → `frontend` (a Vite React SPA served by nginx). The ALB forwards paths verbatim; there is no rewrite. Both workload Services are ClusterIP; nginx additionally keeps an unstripped `/api/*` proxy to `http://ticketmaster` as the in-cluster route.

## Locate Deployment Code

- `.github/workflows/on-push-test.yaml`: deployment trigger and orchestration
- `.github/workflows/called-publish-python-package.yaml`: shared library publication to CodeArtifact
- `.github/workflows/called-publish-docker-images.yaml`: service image build and ECR push (tagged with the Git SHA; includes `rabbitmq-topology`), plus the version-tagged `patroni` image, built only when `infra.postgres.image.tag` is not yet in ECR
- `.github/workflows/called-publish-env-manifests.yaml`: render the chart and commit to the env branch
- `.github/actions/render-manifests/action.yaml`: the one place the render is defined, shared by deploy and PR validation
- `.github/workflows/called-deploy-lambda.yaml`: shared Lambda deployment workflow, parameterized by `package_name`/`handler` — used by both the Cognito PreSignUp Lambda and the S3 Events Lambda
- `.github/workflows/on-pull-request.yaml`: validation gates
- `deploy/chart/`: the single Helm chart — `templates/infra/` (`external-secrets/` with the `eso` ServiceAccount, the two shared ClusterSecretStores, and **every** ExternalSecret in a folder of its own: `frontend/`, `pgbouncer/`, `postgres/`, `rabbitmq/`, `services/ticketmaster/`; `ingress/` with the IngressClass; `services/ticketmaster/` with the backend's workload ServiceAccount; `pgbouncer/` with PgBouncer's ConfigMap, Deployment and Service — see "Run PgBouncer in front of Postgres"; `postgres/` with the `postgres-gp3` StorageClass, the `postgres-patroni` ConfigMap, StatefulSet, Services `postgres-primary` / `postgres-replica`, ServiceAccount, Role and RoleBinding — see "Run Postgres"; `rabbitmq/topology/job.yaml`, the Job that declares the exchange and queues on the managed broker — see "Use managed RabbitMQ"), `templates/services/ticketmaster/` (`http/` with the Deployment + Service + `hpa.yaml`; `background-tasks/worker/` with the TaskIQ worker Deployment; `migrations/{expand,contract}/` with the migration Jobs), `templates/frontend/` (Deployment + Service — no Ingress of its own), a chart-root `templates/ingress.yaml` (the single shared, service-agnostic public ALB Ingress — `/api` rule → `ticketmaster`, `/` catch-all → `frontend`), `values.yaml` (defaults) and `values.test.yaml` (test-eu)
- `env/test-eu` branch: the rendered plain-YAML manifests Argo CD applies. Machine-written by CI only — never commit to it by hand
- `deploy/chart/templates/argocd/application.yaml`: the Argo CD Application `application-test-eu` (namespace `argocd`) — a chart template like everything else, rendered to `env/test-eu`, so **the Application manages its own spec**. Spec changes go through the chart + a `test/**` push, never the UI (selfHeal reverts UI edits). Bootstrap on a fresh cluster is one `helm template --show-only ... | kubectl apply` in `test-stand-up.sh`; after that Argo needs no outside writer
- `src/lambdas/cognito_pre_signup/lambda.yaml`: Cognito PreSignUp Lambda infrastructure
- `src/lambdas/s3_events/lambda.yaml`: S3 Events Lambda infrastructure — dumb forwarder from S3 `ObjectCreated` notifications to `POST /api/admin/s3-events`
- `frontend/{Dockerfile,nginx/}`: the frontend's Docker build and nginx config, deployed via the chart like the other services
- `deploy/_scripts/test-stand-{down,up}.sh`: full delete/recreate of the `test-eu` EKS stand, run via `just test-stand-down` / `just test-stand-up` — see "Treat Teardown as Destructive" below

## Preserve the Release Flow

A push to `test/**` triggers the test deployment. It uses GitHub OIDC, the `deploy-test-eu` concurrency group, and does not cancel an in-progress deployment.

The workflow:

1. `publish-libs` — publish `src/libs` to CodeArtifact.
2. `publish-services-docker-images` — build each service image tagged with the Git SHA and push to ECR. Needs `publish-libs`: the Docker build installs `ticketmaster-libs` from CodeArtifact and must not race the publish.
3. `render-manifests` — needs images. Runs `helm template` on `deploy/chart` with `--set commitSha=$GITHUB_SHA`, then force-replaces the tree on the orphan branch `env/test-eu` and pushes with a GitHub App token (`ticketmaster-env-publisher`). The default `GITHUB_TOKEN` is `contents: read` only: no AWS, no OIDC, no cluster access. The App is the identity that can write `env/**`.

`deploy-cognito-pre-signup-lambda` runs in parallel; it has no `ticketmaster-libs` dependency.

Argo CD (namespace `argocd`) polls `env/test-eu` (~3 min) and syncs Application `application-test-eu`:

```yaml
project: default
source:
  repoURL: https://github.com/Rwwwrl/Ticketmaster.git
  path: .
  targetRevision: env/test-eu
  directory:
    recurse: true
destination:
  server: https://kubernetes.default.svc
  namespace: default
syncPolicy:
  automated:
    prune: true
    selfHeal: true
  retry:
    limit: 5
    backoff:
      duration: 10s
      factor: 2
      maxDuration: 5m
```

**`directory.recurse: true` is mandatory.** Manifests live in nested `infra/` and `services/` directories. Recurse off plus prune on makes desired state empty and deletes everything the Application tracks, including the Ingress (and the ALB). Do not turn recurse off. Do not recreate this Application from scratch unless the user explicitly asks.

**The Application is self-managed.** Its spec is the chart template `deploy/chart/templates/argocd/application.yaml`, rendered onto `env/test-eu` with everything else, so the Application tracks and applies its own manifest. Changing the spec means editing the template (values in `values.test.yaml`) and pushing through the `test/**` pipeline — a `kubectl edit` or Argo UI edit of the live Application is reverted by its own selfHeal on the next sync. The only out-of-band apply is the one bootstrap render in `test-stand-up.sh` on a fresh cluster; never add a second standing writer for it.

The UI is port-forward only. There is no Ingress, LoadBalancer, or SSO for Argo:

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443
# https://localhost:8080  (self-signed cert; user admin)
```

The ordering guarantee is structural: **Argo watches a ref only CI writes, and CI writes it only after the images are pushed.** Never restore a `helm upgrade` or `kubectl apply` step in CI — two writers of the same resources is the failure this design removes. Helm is a render tool in CI, not a cluster release manager. `helm status` / `helm rollback` return nothing. Rollback means reverting the commit on `env/test-eu`, or re-running the pipeline on the previous source commit.

**Sync waves default to `0` in `values.yaml` and are overridden per environment in `values.test.yaml`.** `infra.meta.argocd.syncWave` is `-10` for test-eu; `infra.pgbouncer.meta.argocd.syncWave` and `infra.postgres.meta.argocd.syncWave` are `-8` (after the secrets, before the expand Job that needs the DB; everything under `templates/infra/pgbouncer/**` and `templates/infra/postgres/**` reads its own), and `infra.rabbitmq.topology.meta.argocd.syncWave` is `-5` (the topology Job, which reads it); each backend service's `services.<service>.meta.argocd.syncWave` stays `0`; each backend service's `services.<service>.migrations.expand.meta.argocd.syncWave` is `-5`; each backend service's `services.<service>.migrations.contract.meta.argocd.syncWave` is `5` — `ticketmaster` follows this expand/rollout/contract shape today, and any future backend service should reuse the same four numbers. `frontend` has no migrations, so it carries only `frontend.meta.argocd.syncWave` (`0`), and the chart-root Ingress carries its own `ingress.meta.argocd.syncWave` (also `0` — deliberately not `-10`: an Ingress applied before its backend Service exists never reaches Healthy and deadlocks every later wave). The self-managed Application template reads `argocd.meta.argocd.syncWave`, which is `10` for test-eu — deliberately the **last** wave: Argo's health for an `Application` resource is the app's own aggregate health, so placing it in any earlier wave on a cold rebuild deadlocks the sync (it cannot become Healthy until the workloads it would be gating exist). Every template reads `argocd.argoproj.io/sync-wave: {{ .Values.<tier>.meta.argocd.syncWave | quote }}` rather than hardcoding the string. The wave is a property of the template directory — everything under `templates/infra/**` except the `pgbouncer/`, `postgres/` and `rabbitmq/topology/` folders (every ExternalSecret under `infra/external-secrets/**`, the IngressClass, the backend's ServiceAccount) reads the infra wave; everything under `templates/services/<service>/{http,background-tasks}/**` (Deployment, Service, and for `ticketmaster` also its ServiceAccount and HPA) reads that service's wave; `templates/frontend/**` (Deployment, Service) reads `frontend.meta.argocd.syncWave`; the chart-root `templates/ingress.yaml` reads its own `ingress.meta.argocd.syncWave`; each backend service's `migrations/{expand,contract}/` directory reads its own migration-phase wave. Do not invent per-resource waves, and change the number in `values.yaml`/`values.test.yaml`, not in individual templates. `-5` is shared across every service's expand Job and with the RabbitMQ topology Job — same wave means applied together, and each gates its own completion independently. **Waves are Application-wide, not per-service**: because `ticketmaster` and `frontend` render into one Argo Application, a stuck or failing Job in the backend's chain blocks every wave after it for both (accepted for now — see the isolation tradeoff below). True per-service isolation would need one Argo CD Application per service (each pointing its own `path:` at the same rendered branch, e.g. via an ApplicationSet directory generator over `services/*`); that is not done here. Waves make the sync multi-step, so a Degraded resource now fails the operation and auto-sync will not retry the same commit SHA; the Application's `retry` block covers transient cases, beyond that it needs a manual Sync.

**This wave gating is not Argo's default behavior — it exists only because these templates carry sync-wave annotations.** Without them every resource lands in wave `0` and applies in one pass; a Degraded resource would not block anything else in that same pass. Splitting into waves is what makes a failure upstream stop everything downstream: infra (`-10`) failing means the expand Job (`-5`) is never applied; the expand Job failing means the Deployment (`0`) is never applied; the Deployment failing to become Healthy means the contract Job (`5`) is never applied. The gate sits *between* waves — resources sharing a wave are applied together, so a failure there doesn't block a sibling in the same wave, only later waves.

**`values.yaml` mirrors the template tree, with one exception: `meta`.** A tier's keys generally match its template subdirectories one-to-one (e.g. `infra.externalSecrets.pgbouncer`, `infra.postgres`), but anything that is not a folder — the sync wave, the shared AWS region — lives under that tier's `meta` key instead (`infra.meta.argocd.syncWave`, `infra.meta.region`, `services.ticketmaster.meta.argocd.syncWave`). A folder never appears twice in the tree: all ExternalSecrets live under `infra/external-secrets/<name>/` (their Secrets Manager prefix is `infra.externalSecrets.<name>.prefix`), and everything else a component needs lives in its own `infra/<name>/` folder with its own `meta` wave — never in a second top-level tier. Keep new values inside this convention rather than adding tier-level siblings that aren't folders.

**Do not add `argocd.argoproj.io/sync-options: Prune=false` to the `ExternalSecret`.** Pruning it is recoverable — the value lives in AWS, so reverting the commit brings the `Secret` back. `Prune=false` is reserved for resources holding state the cluster is the only copy of, such as a RabbitMQ `Queue`.

**`commitSha` is chart-level, not per-service.** Every image in this repo is tagged with the same commit SHA, so the chart declares one `commitSha` value and each service template reads it — adding a service never touches CI. Do not reintroduce a per-service `image.tag` value, and do not add a default tag in `values.yaml` — `commitSha` stays `""` there and is always supplied by `--set`. The one exception is `infra.postgres.image.tag` (the `patroni` image, `deploy/images/patroni/`): it is a pinned version tag (also set in `values.test.yaml`, which CI reads), built by a separate CI step only when that tag is missing from ECR, because a commitSha tag would roll the Postgres StatefulSet, and fail over the primary, on every deploy. Any change under `deploy/images/patroni/` must bump that tag.

The action deliberately holds **no** manifest allow-list and no post-render assertions: removing a template is how you remove a resource, and CI is the wrong place to encode the shape of the chart. What catches failure is `helm template` itself under `set -euo pipefail`, plus kubeconform on PRs.

Never add a timestamp or run-number banner to the rendered output — the no-op "nothing to commit" path depends on the render being byte-deterministic.

**Accepted risk:** the Application prunes, so a render that produced no manifests would be a valid commit that wipes the cluster. Nothing in the chart sits behind a conditional today, so it cannot silently shrink. If you ever add `{{- if .Values.x.enabled }}` around a template, revisit that. The self-managed Application sharpens this: deleting `templates/argocd/application.yaml` makes the next sync prune the Application itself — syncing stops and the workloads are orphaned in place (not deleted; the manifest deliberately carries no `resources-finalizer.argocd.argoproj.io` finalizer, and adding one would make self-pruning cascade-delete the whole cluster contents). Recovery is re-running the bootstrap apply from `test-stand-up.sh`.

CI goes green at `git push`, before the deploy lands; there is no `argocd app wait` gate. The cluster is EKS Auto Mode with three static NodePools (one node per AZ, always running while the stand is up), so a deploy pays image pull but not node provisioning before a pod is Ready — check Argo, not the workflow, to know a deploy finished.

Service images must not copy a `poetry.lock`. Service `pyproject.toml` files declare a published `ticketmaster-libs` version; the build resolves it from CodeArtifact using `--build-arg CODEARTIFACT_INDEX_URL` and `--secret id=codeartifact_token`. Never bake the token into a layer.

**Database migrations run expand → rollout → contract, ordered by Argo CD sync waves — the same pattern for every service.** Each service gets two Jobs named `<service>-migrate-expand` (wave `-5`) and `<service>-migrate-contract` (wave `5`), sitting either side of its Deployment's wave `0` — `ticketmaster-migrate-{expand,contract}` today. Both call the shared `ticketmaster.migrationJob` macro in `deploy/chart/templates/_helpers.tpl`, parameterized by `service`, `alembicTarget`, `syncWave`, `imageRepository`, `commitSha`, and `externalSecretName` — adding a service's migration Jobs means two two-line call-site templates, never editing the macro. Never reorder or collapse the sequence; the wave gating enforces it (see above): an expand failure blocks the rollout, and a rollout that never becomes Healthy blocks the contract Job.

Both Jobs are normal tracked resources, not PreSync/PostSync hooks — hooks would run before the ExternalSecret exists on a fresh/rebuilt cluster and deadlock. Each carries `argocd.argoproj.io/sync-options: Force=true,Replace=true`: a Job's `spec.template` is immutable, so Argo's default `kubectl apply` would be rejected on the second deploy once the image tag changes. `Replace=true` switches the verb to `kubectl replace`; `Force=true` makes that replace delete-and-recreate the live object when the plain replace still can't mutate an immutable field. Neither flag alone is sufficient. This re-runs the migration on every sync that re-applies the Job — safe because `alembic upgrade <branch>@head` is idempotent (a no-op once already at head). The Jobs deliberately have **no `ttlSecondsAfterFinished`**: Kubernetes' default is to never delete a finished Job on a TTL, and relying on that default matters here — a TTL-deleted tracked Job goes OutOfSync and selfHeal recreates it, re-running the migration in a loop. Old Jobs persist until the next deploy's Force+Replace swaps them out. Both Jobs use `backoffLimit: 0` (one attempt; a failed migration must fail the sync, not retry into a half-applied state) and label their pods `app: <service>-migrate-<phase>`, distinct from the workload's `app: <service>`, so the Service selector never routes traffic to a migration pod.

The image must contain `alembic.ini` and `migrations/` so the same image SHA serves the app and both migration phases.

## Run PgBouncer in front of Postgres

`pgbouncer` (2 pods, `pool_mode = transaction`, `max_prepared_statements = 200` so asyncpg's statement cache stays on) sits between the app and the in-cluster Postgres (`postgres-primary.default.svc.cluster.local`, database `ticketmaster`, user `ticketmaster`). The app uses `POSTGRES_POOLER_DB_URL` (`pgbouncer.default.svc.cluster.local:5432/ticketmaster` → `postgres-primary`) for writes and `POSTGRES_POOLER_RO_DB_URL` (`.../ticketmaster_ro` → `postgres-replica`, load-balanced over the replicas) for stale-tolerant reads; **migration Jobs and test fixtures use `POSTGRES_DIRECT_DB_URL` and must never go through PgBouncer** (DDL plus PgBouncer's shared prepared statements leaves stale statements, pgbouncer#1038). `pgbouncer.ini` is a git-tracked ConfigMap (`track_extra_parameters = IntervalStyle, statement_timeout` is required: the app sends `statement_timeout` at connect time, and PgBouncer rejects startup parameters it doesn't track; the pod template carries a `checksum/config` annotation, so a change rolls pods). The userlist is a single Secrets Manager secret `ticketmaster/pgbouncer/test-eu/USERLIST_TXT` (`"ticketmaster" "<APP_PASSWORD>"` — plain, because PgBouncer logs in to the server with it), synced by ESO as `userlist.txt`. A userlist change needs no action: ESO updates the Secret, kubelet updates the mounted file in place, and the `userlist-reloader` sidecar (same image, `shareProcessNamespace: true`) sends PgBouncer SIGHUP, which re-reads `auth_file` without dropping connections. Never change a column's type in place (see the `sqlmodel` skill) — PgBouncer's shared prepared statements would keep failing with `cached plan must not change result type` until every PgBouncer reconnects (pgbouncer#1038, unfixed upstream). There is no admin user: `kubectl exec deploy/pgbouncer -c pgbouncer -- psql -h /tmp -U pgbouncer pgbouncer` uses the Unix socket, where PgBouncer grants admin to its own uid. There is deliberately no `preStop` drain: on SIGTERM PgBouncer waits for clients to disconnect, which pooled clients never do, so a stopping pod keeps serving its existing connections for the 30 s grace period and is then killed; the app reconnects (`pool_pre_ping`) and only in-flight transactions at that moment fail.

## Run Postgres

`postgres` is a StatefulSet of **three** pods (`postgres-0..2`), one per AZ, each running Patroni as PID 1 over PostgreSQL 18 from the `patroni` image (`deploy/images/patroni/`: stock `postgres:18.6-trixie` pinned by digest + the PGDG `patroni` deb). Each pod has its own 10Gi encrypted gp3 PVC `pgdata-postgres-N` from StorageClass `postgres-gp3` (`ebs.csi.eks.amazonaws.com`, `WaitForFirstConsumer`, `reclaimPolicy: Delete`). The volume is zonal, so the PV pins the pod to its AZ; while that AZ's node is gone the pod stays `Pending` (no relocation) and the cluster runs on two members. Replication is `synchronous_mode: quorum`, `synchronous_node_count: 1`, i.e. `synchronous_standby_names = ANY 1 (…)` with `synchronous_commit = on`; non-strict, so with no replica left Patroni goes async instead of blocking writes. Services: `postgres-primary` (`app: postgres, role: primary`, what PgBouncer and the migration Jobs connect to) and `postgres-replica` (`role: replica`). Patroni sets the `role` pod label; **never put `role` in the pod template**. There is deliberately no headless Service and no `serviceName`: members find each other by pod IP from the DCS. `podManagementPolicy: Parallel` is required (with `OrderedReady` an ineligible `postgres-0` can block 1..2 after a full restart); `selector` and `volumeClaimTemplates` are immutable.

- **DCS is the Kubernetes API (ConfigMaps, `use_endpoints: false`).** Patroni creates `postgres-config` (initialize key, dynamic config), `postgres-leader`, `postgres-sync` and, during a failover, `postgres-failover`; member state is a `status` annotation on each pod. **Never render these in Helm**, and never give our own ConfigMap those names or the `cluster-name` label: `patronictl remove` and the stale-DCS reset delete by that label selector. Our ConfigMap is `postgres-patroni` (`patroni.yml` + `post-bootstrap.sh`, mounted at `/etc/patroni` with mode `0555`).
- **`cluster-name: postgres` on the pods is required:** Patroni always adds `cluster-name: <scope>` to `kubernetes.labels`; that set is the selector it lists members with. `PATRONI_KUBERNETES_LABELS` is `{app: postgres}` — never add Argo's instance label there, Patroni copies these labels onto its DCS ConfigMaps.
- **`bootstrap.dcs` is one-shot:** written to `postgres-config` at initdb and ignored afterwards. Later changes go through `patronictl edit-config`; local `postgresql.parameters` and `pg_hba` win over the DCS and reload with `patronictl reload`. Changing the `postgres-patroni` ConfigMap rolls the pods via the `checksum/config` annotation, and rolling the primary is a failover.
- **Mount at `/var/lib/postgresql`; `data_dir` is `/var/lib/postgresql/18/main`** (a subdirectory, because the volume root holds `lost+found`). `securityContext` is only `fsGroup: 999` + `fsGroupChangePolicy: OnRootMismatch`: uid 999 needs the group to create the data dir on a fresh root-owned volume, and the default `Always` would add group write to PGDATA (`2770`), which Postgres 18 refuses to start on.
- **First boot:** the three pods race for the `initialize` key on empty volumes. The winner runs initdb, then `post-bootstrap.sh` (creates role and database `ticketmaster` with `APP_PASSWORD`; Patroni strips `PATRONI_*` variables from its environment, hence the plain `APP_DB_PASSWORD`), takes the leader lock and gets `role=primary`; the others `pg_basebackup` from it. If `post-bootstrap.sh` fails, Patroni renames the data dir to `.failed` and the race restarts.
- **Diverged old primary:** `use_pg_rewind: true` — the old primary copies only the differing blocks from the new one with `pg_rewind` and streams its WAL; its extra, never-acknowledged commits are discarded. Only if the rewind fails (or the timelines can't be rewound) do `remove_data_directory_on_rewind_failure` / `remove_data_directory_on_diverged_timelines` wipe the member and re-clone it.
- **Secrets:** Secrets Manager `ticketmaster/postgres/test-eu/{SUPERUSER_PASSWORD,APP_PASSWORD,REPLICATION_PASSWORD,REWIND_PASSWORD,RESTAPI_PASSWORD}`, synced by ESO into Secret `postgres`. The app password also lives in `USERLIST_TXT` and in both `POSTGRES_*_DB_URL` secrets; rotating it means updating all four and running `ALTER ROLE`. Generate with `openssl rand -hex 24` so it stays URL-safe.
- **Operations** (`kubectl exec -it postgres-0 -- patronictl …`; these mutate runtime state, not manifests): `list`; `switchover --leader <current> [--candidate postgres-2] --force`; `failover --candidate postgres-2 --force` (unhealthy cluster only); `edit-config --force -s ttl=30 -p max_connections=150`; `reload postgres --force`; `restart postgres --pending --force`; `reinit postgres postgres-2 --force`.
- **Stale DCS + wiped PVCs = stuck forever** (`postgres-config` still holds an old `initialize` and there is no leader, so new pods sit at `waiting for leader to bootstrap`). Reset: commit `replicas: 0` (`whenScaled: Delete` drops the PVCs), `kubectl delete cm -l app=postgres,cluster-name=postgres`, commit `replicas: 3`. Never delete the DCS ConfigMaps while Patroni runs. A full stand-down/up wipes both and is unaffected.
- **Primary evictions** (node drain, `kubectl delete nodeclaim`, node failure, node expiry) are fast failovers with dropped connections. There is deliberately no PodDisruptionBudget (draining one node evicts its single Postgres pod; never drain two nodes at once) and no `preStop` switchover hook.
- **Statement timeouts are per connection, not per role.** The app engine (`init_sqlmodel_engine`) sends `statement_timeout=15s` (PgBouncer must track it, see above) and deliberately has no asyncpg `command_timeout`: a client cancel can be lost behind two PgBouncer pods because it opens a new connection, and the 20s `RequestTimeoutMiddleware` bounds every request, so the 15s `statement_timeout` always fires first. A statement timeout (SQLSTATE 57014, wrapped by SQLAlchemy in a plain `DBAPIError`) is mapped to 504 `{"detail": "The server took too long to respond. Please retry later."}` by `database_exception_handler` (`libs.fastapi_ext.exception_handlers`, registered in `http/main.py`), which also maps connectivity errors during a failover to 503 + `Retry-After: 5`; any other `DBAPIError` is re-raised to `UnhandledExceptionMiddleware`. Migrations (`run_alembic`, direct URL) set `transaction_timeout=75s` and no `statement_timeout`.
- Probes are Patroni's REST API on 8008: readiness `GET /readiness` (leader, or a streaming replica within `maximum_lag_on_failover`), liveness `GET /liveness` (the HA loop is alive; it runs no SQL). `STOPSIGNAL SIGTERM` (the base image's SIGINT is reset) so Patroni handles shutdown.

## Use managed RabbitMQ

The broker is **not** in the cluster: RabbitMQ is a managed cloud service, so there is no StatefulSet, PVC or StorageClass to run, and nothing to tear down in `test-stand-down.sh`. The cluster only holds the connection string and one Job. The broker must support quorum queues and AMQP 0-9-1, and its vhost and user are created in the provider's console.

- **Secrets Manager** (create before the first push, or the ExternalSecret goes Degraded and stops wave `-10`): `ticketmaster/rabbitmq/test-eu/RABBITMQ_URL` (read by the topology Job, ExternalSecret `rabbitmq`) and `ticketmaster/ticketmaster/test-eu/RABBITMQ_URL` (read by the worker, ExternalSecret `ticketmaster`). Both hold the provider's full `amqps://user:password@host/vhost` URL; the user needs configure, write and read permissions on the vhost. Rotating the credential means updating both secrets; ESO syncs within the hour (or on the next deploy, via `force-sync`), and pods only pick it up on restart.
- **ECR repository `rabbitmq-topology`** is created by hand like `ticketmaster` and `frontend`.
- **Topology is owned by the `rabbitmq-topology` Job** (wave `-5`, image from `src/rabbitmq_topology`, tagged with `commitSha`, so it re-runs on every deploy). It declares everything listed in `rabbitmq_topology/resources.py` (`EXCHANGES`, `DEAD_LETTER_QUEUES`, `QUEUES`, `DELAY_QUEUES`, `BINDINGS`), the same shape as eshop2. Nothing else depends on `src/rabbitmq_topology`: it is not published to CodeArtifact, and the worker refers to the same exchange and queue names itself, only checking them passively.
- **Queue arguments are immutable.** A changed argument fails the Job with `406 PRECONDITION_FAILED` and stops the sync at wave `-5` (frontend included). To change one, use a broker policy (mutable) or delete the queue in the provider's console (which drops its messages) and let the next deploy re-create it.
- **Never set `x-max-priority`** on these queues; quorum queues reject it.
- **Worker:** Deployment `ticketmaster-worker` (label `app: ticketmaster-worker`, never `app: ticketmaster` or the http Service and HPA selectors capture it), same image, `ticketmaster` ServiceAccount and Secret as the http Deployment; `taskiq worker --workers 1 --max-async-tasks 10 --wait-tasks-timeout 65 --shutdown-timeout 10` with `terminationGracePeriodSeconds: 90`. No probes, no Service.

## Keep Environment Configuration Complete

Use `eu-central-1` consistently in GitHub variables, resource ARNs, and `kms:ViaService` conditions.

Use these path conventions:

```text
/ticketmaster/<env>/<key>
/ticketmaster/<service>/<env>/<key>
```

Store non-secret configuration in SSM and sensitive values in Secrets Manager. Postgres's own secrets live under `ticketmaster/postgres/test-eu/`. Backend secrets currently include `POSTGRES_DIRECT_DB_URL`, `POSTGRES_POOLER_DB_URL`, `POSTGRES_POOLER_RO_DB_URL`, `REDIS_URL`, `SECRET`, and `SENTRY_DSN`.

In CloudFormation `ValueFrom` — no template in the repo uses this any more; the Lambda's `lambda.yaml` resolves its one KMS ARN via SSM's `{{resolve:ssm:...}}` instead, which has no ARN-suffix quirk. An ExternalSecret's `remoteRef.key` uses the plain secret/parameter name instead — no ARN involved.

`ticketmaster` consumes twenty values and `frontend` consumes four; the ExternalSecret/ClusterSecretStore plumbing is identical across both and is the reference for every service that follows:

- `ticketmaster`: `POSTGRES_DIRECT_DB_URL`, `POSTGRES_POOLER_DB_URL`, `POSTGRES_POOLER_RO_DB_URL`, `REDIS_URL`, `RABBITMQ_URL`, `SECRET`, `SENTRY_DSN` from Secrets Manager `ticketmaster/ticketmaster/test-eu/*`; `ENVIRONMENT`, `SENTRY_SEND_PII`, `SENTRY_TRACES_SAMPLE_RATE`, `AWS_REGION`, `CDN_DOMAIN`, `JWT_AUDIENCE`, `LAMBDA_JWT_KMS_KEY_ARN`, `LAMBDA_JWT_ISSUER`, `ADMIN_JWT_KMS_KEY_ARN`, `ADMIN_JWT_ISSUER`, `COGNITO_AUDIENCE`, `S3_EVENTS_JWT_KMS_KEY_ARN`, `S3_EVENTS_JWT_ISSUER` from SSM `/ticketmaster/ticketmaster/test-eu/*`. S3 bucket names are not settings at all — they live as literal values in `S3BucketEnum` (`ticketmaster.enums`), e.g. `MEDIA_PUBLIC = "ticketmaster-test-eu-media-public"`. The media bucket is private (Block Public Access fully on; its policy grants only the CloudFront service principal, scoped by `AWS:SourceArn` to one distribution via Origin Access Control). The event trailer's public URL is derived from `CDN_DOMAIN` plus the object key at serialize time (`ticketmaster.serializers.ToEventResponseSchemaSerializer`, via `libs.aws.utils.build_cdn_object_url`), never stored. The distribution's cache policy is the managed `CachingOptimized` (24h default TTL, since trailer objects carry no `Cache-Control`); trailer keys are immutable UUIDs per upload, so a new upload is always a cache miss and no invalidation is needed — but a deleted trailer still serves from an edge until its TTL expires. The CloudFront cert must be in `us-east-1` (CloudFront-wide requirement), unlike every other cert here, and is a separate resource from the `eu-central-1` ALB cert. The s3_events Lambda's `s3:GetObject` (needed for `HeadObject`) is account-wide in its CloudFormation template, not scoped to this bucket, precisely so a bucket rename touches only the enum. `AWS_REGION` has no other source on EKS — the ECS runtime injected it into every container automatically; here it's a plain SSM parameter routed through the ExternalSecret like everything else, so the shared migration-Job macro (which also constructs the full `Settings` object) needs no special-casing.
- `frontend`: `BACKEND_URL`, `COGNITO_USER_POOL_ID`, `COGNITO_USER_POOL_CLIENT_ID`, `COGNITO_DOMAIN`, all from SSM `/ticketmaster/frontend/test-eu/*`. `BACKEND_URL` is the in-cluster address of the `ticketmaster` Service (`http://ticketmaster`, no trailing slash — nginx's `proxy_pass ${BACKEND_URL};` forwards `/api/...` verbatim; the backend serves it natively), not an external URL; it is envsubst'd into nginx's `default.conf` by the stock nginx entrypoint at container start. The Cognito three are envsubst'd into a static `config.js` the SPA loads at runtime by a custom `/docker-entrypoint.d/30-render-config.sh` script.
- Each service's own `ExternalSecret` reads all of its keys — `spec.data[].sourceRef.storeRef` names a store per key (`aws-secret-store-secrets-manager`, `aws-secret-store-parameter-store`) — and writes one Kubernetes `Secret` named after the service, which its Deployment (and, for the backend, its two migration Jobs) consume with `envFrom`.
- **Two `ClusterSecretStore`s are required, not a style choice — and they are shared, not per-service.** A store holds one `spec.provider`, and the AWS provider's `service` is a scalar: `SecretsManager` or `ParameterStore`, so one store per provider is the minimum regardless of how many services exist. `aws-secret-store-secrets-manager` and `aws-secret-store-parameter-store` live under `templates/infra/external-secrets/` and are provider-scoped, not service-scoped — every service's `ExternalSecret` points at the same two stores. Neither sets `spec.conditions` to restrict which namespace may use it — only `default` exists — and `eso`'s IAM policy is account-wide read (see below), so a namespace condition would harden against nothing real. Each store's `auth.jwt.serviceAccountRef.namespace` is required, though — that field is mandatory for a `ClusterSecretStore` per ESO's docs, unlike a namespaced `SecretStore`.
- **Auth is IRSA and cannot be Pod Identity.** Both stores use `auth.jwt.serviceAccountRef` → the chart's shared `eso` ServiceAccount; ESO mints a token for that SA and calls `sts:AssumeRoleWithWebIdentity`. ESO cannot impersonate a Pod-Identity-bound service account. This is why `eso` and a workload's own AWS identity are necessarily two different mechanisms — see the `ticketmaster` bullet below.
- **One shared ServiceAccount, one IAM role, deliberately account-wide, deliberately not split per service.** `eso`'s IAM role (`ticketmaster-test-eu-eso`) holds the AWS managed policies `AmazonSSMReadOnlyAccess` and `AWSSecretsManagerClientReadOnlyAccess` — every SSM parameter and Secrets Manager secret in the account, not scoped to per-service ARN prefixes. This was a deliberate choice when `ticketmaster` was added as the second service consuming `eso`: a single shared, service-agnostic controller identity was preferred over per-service IAM scoping or a chained per-service role. Do not narrow this to per-service ARNs and do not create a second ESO ServiceAccount/role per service — that reintroduces the isolation `eso` was designed to avoid.
- The `frontend` pod does not set `serviceAccountName` — it runs as the namespace's `default` SA. It makes no AWS calls, so giving it its own ServiceAccount would be unused plumbing.
- **`ticketmaster` does make AWS calls at runtime** (`kms:GetPublicKey` on its two JWT signing keys, `cognito-idp:AdminDeleteUser`, and S3 `PutObject`/`GetObject`/`DeleteObject` on the media bucket via the `AmazonS3FullAccess` managed policy — presigned trailer uploads and deleting a trailer's object on event delete), so it runs under its own ServiceAccount, bound to an IAM role via **EKS Pod Identity**. That ServiceAccount lives at `templates/infra/services/ticketmaster/service-account.yaml`, beside the service's ExternalSecret rather than beside its workload: it is AWS-identity wiring, so it follows the same infra-tree convention (and the same `-10` wave, so the SA exists before the Deployment that references it) — a *different* mechanism from `eso`'s IRSA, deliberately: Pod Identity associations (`aws eks create-pod-identity-association`) are the more direct fit for a workload's own AWS access, while ESO specifically requires IRSA. The ticketmaster ServiceAccount carries no `eks.amazonaws.com/role-arn` annotation (that's IRSA-only); Pod Identity binds by association, not by SA annotation. Do not let a workload pod use the `eso` ServiceAccount as its own identity, and do not add an IRSA role-arn annotation to a Pod-Identity-bound ServiceAccount.
- The `ExternalSecret` carries `force-sync: {{ .Values.commitSha }}`, which makes every deploy bump `resourceVersion` so ESO re-reads AWS. Never replace it with a `kubectl annotate` step in CI.
- `Settings` subclasses `libs.settings.BaseAppSettings` (and, for `ticketmaster`, several more mixins), so a missing required value fails at import and the pod — or a migration Job — never becomes Ready/Complete. That is intentional.

Adding a backend service means: its own `ExternalSecret` under `templates/infra/external-secrets/services/<service>/`, referencing the existing shared `aws-secret-store-*` ClusterSecretStores — not new stores, and not a new ESO ServiceAccount. If the service makes its own AWS calls, give it its own workload ServiceAccount bound via EKS Pod Identity (never via the `eso` ServiceAccount). `frontend` is the one exception to the `external-secrets/services/<service>/` path: since it isn't a peer of `services/<service>/` in the template tree (it's `templates/frontend/`, not `templates/services/frontend/`), its ExternalSecret lives at `templates/infra/external-secrets/frontend/` instead.

Whenever a required setting is added or renamed, update the chart or CloudFormation template that injects it, update test environment configuration, and ensure the value exists in SSM or Secrets Manager for `test-eu`.

Preserve least-privilege roles. The Lambda role signs with its specific KMS key.

Expected GitHub environment variables: `AWS_REGION`, `AWS_ACCOUNT_ID`, `DEPLOYER_TO_AWS_ROLE_ARN`, `CODEARTIFACT_DOMAIN`, `CODEARTIFACT_REPOSITORY`, and `EKS_CLUSTER_NAME`.

## Prepare a Deployment Change

Before an explicitly requested deploy:

1. Inspect the branch and exact diff.
2. Confirm the target is `test-eu` in `eu-central-1`.
3. Bump package versions for changes under `src/libs/` or `src/ticketmaster/`. If the shared library version is unchanged, publication may skip it and services can install old code.
4. Verify settings are mirrored in the chart or the relevant CloudFormation template.
5. Validate code, tests, manifests, and CloudFormation.
6. Report the exact branch, image/service scope, environment, and region.
7. Push or rerun a workflow only when the user's request authorizes that external mutation.

Do not expose secret values or CodeArtifact tokens in commands, logs, templates, or responses.

Run the PR-equivalent checks:

```bash
poetry run ruff check .
poetry run ruff format --check .
poetry run pytest --cov=src/libs/libs --cov=src/ticketmaster/ticketmaster --cov-report=term-missing --cov-fail-under=75
cfn-lint src/lambdas/cognito_pre_signup/lambda.yaml src/lambdas/s3_events/lambda.yaml
helm template ticketmaster ./deploy/chart \
  -f ./deploy/chart/values.test.yaml \
  --set commitSha=dummy --output-dir /tmp/rendered
kubeconform -strict -summary -schema-location default \
  -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' \
  /tmp/rendered
```

## Diagnose Without Mutating

For explanation, status, review, or diagnosis requests, remain read-only. Inspect workflow runs, failed logs, pod status, and readiness without pushing, rerunning, deploying, or changing AWS or cluster resources.

Useful read-only commands include:

```bash
gh run list --workflow on-push-test.yaml --branch <test-branch>
gh run view <run-id> --log-failed
aws eks update-kubeconfig --name ticketmaster-test-eu --region eu-central-1
kubectl get pods,svc,ingress
kubectl describe pod <pod>
kubectl logs deploy/ticketmaster
kubectl -n argocd port-forward svc/argocd-server 8080:443
argocd app get application-test-eu
argocd app history application-test-eu
git log --oneline origin/env/test-eu
aws cloudformation describe-stack-events --stack-name ticketmaster-cognito-pre-signup-test-eu --region eu-central-1
```

There is no Helm release any more, so `helm status`, `helm history` and `helm rollback` all return nothing. Rollback means reverting the commit on `env/test-eu`, or re-running the pipeline on the previous source commit. Argo is reachable only through `kubectl port-forward` today. `selfHeal` reverts a manual `kubectl edit` of tracked resources; that is intended.

The stand is reachable at the stable domain `https://test-eu.as-ticketmaster.com` (Route53 alias to the ALB, refreshed by `test-stand-up.sh` — see below), or via the raw Ingress hostname for debugging: read `status.loadBalancer.ingress[0].hostname` before probing `/readiness-check` there. TLS terminates at the ALB via an ACM certificate (`arn:aws:acm:eu-central-1:258167965416:certificate/43c8134a-af07-4b42-98e2-6dd086cabee7`, referenced by `ingress.meta.certificateArn` in `deploy/chart/values.test.yaml`); the Ingress listens on both 80 (redirects to 443) and 443. Chart endpoints are hyphenated (`/health-check`, `/readiness-check`) for `ticketmaster`; `frontend`'s nginx exposes only `/readiness-check` (no separate `/health-check` — a static file server has no meaningful liveness/readiness distinction), used for both its liveness and readiness probes and as the shared Ingress's ALB healthcheck-path.

Capacity is fixed at three `t3a.medium` nodes (2 vCPU, 4 GiB each), so a `Pending` pod usually means it doesn't fit, or its zone's node is being replaced (node expiry, or a manual `kubectl delete nodeclaim`). Check `kubectl get nodes,nodeclaims` before diagnosing further. Right after `test-stand-up` the nodes may still be joining.

## Treat Teardown as Destructive

`just test-stand-down` and `just test-stand-up` (`deploy/_scripts/test-stand-{down,up}.sh`) fully delete and recreate the `test-eu` EKS stand — the user's opt-in way to stop paying for an idle cluster between test sessions. `test-stand-down` suspends Argo auto-sync, deletes the Ingress (waiting for the ALB controller's finalizer to actually remove the ALB), deletes the cluster's IAM OIDC provider, deletes the Postgres StatefulSet and its PVCs (EBS volumes can outlive `delete-cluster`, and the stand can't be rebuilt around a leaked one), then deletes the EKS cluster itself — nodes, EBS volumes, access entries, and the Pod Identity association go with it. `test-stand-up` recreates the cluster from the config recorded in the script, re-creates the OIDC provider and rewires the `ticketmaster-test-eu-eso` IRSA trust policy to it (the issuer changes on every recreate), recreates the Pod Identity association, creates the Auto Mode NodeClass `static` and one static NodePool per subnet/AZ (`static-<az>`, `replicas: 1`, `t3a.medium`, drift replacement blocked, `expireAfter: 480h`) with `kubectl apply` and waits for the three nodes — Auto Mode has no AWS API for custom pools, so the script, not Argo, owns them; change a pool by editing the script and re-running it, and roll a node with `kubectl delete nodeclaim <name>` — reinstalls the External Secrets Operator and Argo CD, and bootstraps the Application by rendering the chart's `templates/argocd/application.yaml` locally (`helm template --show-only ... | kubectl apply`) — Argo then restores the whole app from `env/test-eu` with no CI run needed, and from that point the Application manages its own spec from the rendered branch. Because the ALB gets a new hostname each cycle, `test-stand-up` upserts a Route53 alias record (`test-eu.as-ticketmaster.com`, hosted zone `Z03658353OC69AMXF8YCD`) pointing at the new ALB, then refreshes the stable `https://test-eu.as-ticketmaster.com` URL in the `TICKETMASTER_API_URL` SSM parameter and the Cognito pre-signup Lambda's environment. The Cognito app client's allowed callback/sign-out URLs are console-managed and use this same stable domain, so they only need setting once.

Kept across a down/up cycle (not billed meaningfully, or hold data): IAM roles, KMS keys, Secrets Manager secrets, other SSM parameters, the Cognito user pool, ECR images, the Cognito pre-signup Lambda's CloudFormation stack, Redis (external to this account), the `as-ticketmaster.com` domain registration and hosted zone, the ACM certificate (auto-renews via its kept DNS validation record — never delete it), and — independent of the cluster entirely — the media CloudFront distribution, its `us-east-1` ACM certificate, and the `media.test-eu.as-ticketmaster.com` Route53 alias record.

These recipes are user-invoked only — never run `just test-stand-down` or `just test-stand-up` on your own initiative, and never delete AWS resources, CloudFormation stacks, ECR repositories, or the Argo CD Application by any other means without the user explicitly asking. Deleting an Application with `prune: true` deletes every resource it tracks. For a teardown request beyond what these two recipes cover, produce the ordered console/CLI steps and let the user execute them.

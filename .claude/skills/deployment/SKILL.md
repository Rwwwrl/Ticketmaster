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
- `.github/workflows/called-publish-docker-images.yaml`: service image build and ECR push
- `.github/workflows/called-publish-env-manifests.yaml`: render the chart and commit to the env branch
- `.github/actions/render-manifests/action.yaml`: the one place the render is defined, shared by deploy and PR validation
- `.github/workflows/called-deploy-lambda.yaml`: Cognito PreSignUp Lambda deployment
- `.github/workflows/on-pull-request.yaml`: validation gates
- `deploy/chart/`: the single Helm chart — `templates/infra/` (`external-secrets/` with the `eso` ServiceAccount and the two shared ClusterSecretStores, `ingress/` with the IngressClass, `services/ticketmaster/` with the backend's ExternalSecret and workload ServiceAccount, and `frontend/` with the frontend's ExternalSecret), `templates/services/ticketmaster/` (`http/` with the Deployment + Service + `hpa.yaml`; `migrations/{expand,contract}/` with the migration Jobs), `templates/frontend/` (Deployment + Service — no Ingress of its own), a chart-root `templates/ingress.yaml` (the single shared, service-agnostic public ALB Ingress — `/api` rule → `ticketmaster`, `/` catch-all → `frontend`), `values.yaml` (defaults) and `values.test.yaml` (test-eu)
- `env/test-eu` branch: the rendered plain-YAML manifests Argo CD applies. Machine-written by CI only — never commit to it by hand
- `deploy/chart/templates/argocd/application.yaml`: the Argo CD Application `application-test-eu` (namespace `argocd`) — a chart template like everything else, rendered to `env/test-eu`, so **the Application manages its own spec**. Spec changes go through the chart + a `test/**` push, never the UI (selfHeal reverts UI edits). Bootstrap on a fresh cluster is one `helm template --show-only ... | kubectl apply` in `test-stand-up.sh`; after that Argo needs no outside writer
- `src/lambdas/cognito_pre_signup/lambda.yaml`: Lambda infrastructure
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

**Sync waves default to `0` in `values.yaml` and are overridden per environment in `values.test.yaml`.** `infra.meta.argocd.syncWave` is `-10` for test-eu; each backend service's `services.<service>.meta.argocd.syncWave` stays `0`; each backend service's `services.<service>.migrations.expand.meta.argocd.syncWave` is `-5`; each backend service's `services.<service>.migrations.contract.meta.argocd.syncWave` is `5` — `ticketmaster` follows this expand/rollout/contract shape today, and any future backend service should reuse the same four numbers. `frontend` has no migrations, so it carries only `frontend.meta.argocd.syncWave` (`0`), and the chart-root Ingress carries its own `ingress.meta.argocd.syncWave` (also `0` — deliberately not `-10`: an Ingress applied before its backend Service exists never reaches Healthy and deadlocks every later wave). The self-managed Application template reads `argocd.meta.argocd.syncWave`, which is `10` for test-eu — deliberately the **last** wave: Argo's health for an `Application` resource is the app's own aggregate health, so placing it in any earlier wave on a cold rebuild deadlocks the sync (it cannot become Healthy until the workloads it would be gating exist). Every template reads `argocd.argoproj.io/sync-wave: {{ .Values.<tier>.meta.argocd.syncWave | quote }}` rather than hardcoding the string. The wave is a property of the template directory — everything under `templates/infra/**` (including each backend service's ExternalSecret at `infra/services/<service>/` and the frontend's ExternalSecret at `infra/frontend/`, neither living beside its workload) reads the infra wave; everything under `templates/services/<service>/http/**` (Deployment, Service, and for `ticketmaster` also its ServiceAccount and HPA) reads that service's wave; `templates/frontend/**` (Deployment, Service) reads `frontend.meta.argocd.syncWave`; the chart-root `templates/ingress.yaml` reads its own `ingress.meta.argocd.syncWave`; each backend service's `migrations/{expand,contract}/` directory reads its own migration-phase wave. Do not invent per-resource waves, and change the number in `values.yaml`/`values.test.yaml`, not in individual templates. `-5` is shared across every service's expand Job and with the RabbitMQ topology Job when it lands — same wave means applied together, and each gates its own completion independently. **Waves are Application-wide, not per-service**: because `ticketmaster` and `frontend` render into one Argo Application, a stuck or failing Job in the backend's chain blocks every wave after it for both (accepted for now — see the isolation tradeoff below). True per-service isolation would need one Argo CD Application per service (each pointing its own `path:` at the same rendered branch, e.g. via an ApplicationSet directory generator over `services/*`); that is not done here. Waves make the sync multi-step, so a Degraded resource now fails the operation and auto-sync will not retry the same commit SHA; the Application's `retry` block covers transient cases, beyond that it needs a manual Sync.

**This wave gating is not Argo's default behavior — it exists only because these templates carry sync-wave annotations.** Without them every resource lands in wave `0` and applies in one pass; a Degraded resource would not block anything else in that same pass. Splitting into waves is what makes a failure upstream stop everything downstream: infra (`-10`) failing means the expand Job (`-5`) is never applied; the expand Job failing means the Deployment (`0`) is never applied; the Deployment failing to become Healthy means the contract Job (`5`) is never applied. The gate sits *between* waves — resources sharing a wave are applied together, so a failure there doesn't block a sibling in the same wave, only later waves.

**`values.yaml` mirrors the template tree, with one exception: `meta`.** A tier's keys generally match its template subdirectories one-to-one (e.g. `infra.externalSecrets`, `infra.services`), but anything that is not a folder — the sync wave, the shared AWS region — lives under that tier's `meta` key instead (`infra.meta.argocd.syncWave`, `infra.meta.region`, `services.ticketmaster.meta.argocd.syncWave`). Keep new values inside this convention rather than adding tier-level siblings that aren't folders.

**Do not add `argocd.argoproj.io/sync-options: Prune=false` to the `ExternalSecret`.** Pruning it is recoverable — the value lives in AWS, so reverting the commit brings the `Secret` back. `Prune=false` is reserved for resources holding state the cluster is the only copy of, such as a RabbitMQ `Queue`.

**`commitSha` is chart-level, not per-service.** Every image in this repo is tagged with the same commit SHA, so the chart declares one `commitSha` value and each service template reads it — adding a service never touches CI. Do not reintroduce a per-service `image.tag` value, and do not add a default tag in `values.yaml` — `commitSha` stays `""` there and is always supplied by `--set`.

The action deliberately holds **no** manifest allow-list and no post-render assertions: removing a template is how you remove a resource, and CI is the wrong place to encode the shape of the chart. What catches failure is `helm template` itself under `set -euo pipefail`, plus kubeconform on PRs.

Never add a timestamp or run-number banner to the rendered output — the no-op "nothing to commit" path depends on the render being byte-deterministic.

**Accepted risk:** the Application prunes, so a render that produced no manifests would be a valid commit that wipes the cluster. Nothing in the chart sits behind a conditional today, so it cannot silently shrink. If you ever add `{{- if .Values.x.enabled }}` around a template, revisit that. The self-managed Application sharpens this: deleting `templates/argocd/application.yaml` makes the next sync prune the Application itself — syncing stops and the workloads are orphaned in place (not deleted; the manifest deliberately carries no `resources-finalizer.argocd.argoproj.io` finalizer, and adding one would make self-pruning cascade-delete the whole cluster contents). Recovery is re-running the bootstrap apply from `test-stand-up.sh`.

CI goes green at `git push`, before the deploy lands; there is no `argocd app wait` gate. The cluster is EKS Auto Mode and scales from zero, so a cold deploy pays node provisioning plus image pull before any pod is Ready — check Argo, not the workflow, to know a deploy finished.

Service images must not copy a `poetry.lock`. Service `pyproject.toml` files declare a published `ticketmaster-libs` version; the build resolves it from CodeArtifact using `--build-arg CODEARTIFACT_INDEX_URL` and `--secret id=codeartifact_token`. Never bake the token into a layer.

**Database migrations run expand → rollout → contract, ordered by Argo CD sync waves — the same pattern for every service.** Each service gets two Jobs named `<service>-migrate-expand` (wave `-5`) and `<service>-migrate-contract` (wave `5`), sitting either side of its Deployment's wave `0` — `ticketmaster-migrate-{expand,contract}` today. Both call the shared `ticketmaster.migrationJob` macro in `deploy/chart/templates/_helpers.tpl`, parameterized by `service`, `alembicTarget`, `syncWave`, `imageRepository`, `commitSha`, and `externalSecretName` — adding a service's migration Jobs means two two-line call-site templates, never editing the macro. Never reorder or collapse the sequence; the wave gating enforces it (see above): an expand failure blocks the rollout, and a rollout that never becomes Healthy blocks the contract Job.

Both Jobs are normal tracked resources, not PreSync/PostSync hooks — hooks would run before the ExternalSecret exists on a fresh/rebuilt cluster and deadlock. Each carries `argocd.argoproj.io/sync-options: Force=true,Replace=true`: a Job's `spec.template` is immutable, so Argo's default `kubectl apply` would be rejected on the second deploy once the image tag changes. `Replace=true` switches the verb to `kubectl replace`; `Force=true` makes that replace delete-and-recreate the live object when the plain replace still can't mutate an immutable field. Neither flag alone is sufficient. This re-runs the migration on every sync that re-applies the Job — safe because `alembic upgrade <branch>@head` is idempotent (a no-op once already at head). The Jobs deliberately have **no `ttlSecondsAfterFinished`**: Kubernetes' default is to never delete a finished Job on a TTL, and relying on that default matters here — a TTL-deleted tracked Job goes OutOfSync and selfHeal recreates it, re-running the migration in a loop. Old Jobs persist until the next deploy's Force+Replace swaps them out. Both Jobs use `backoffLimit: 0` (one attempt; a failed migration must fail the sync, not retry into a half-applied state) and label their pods `app: <service>-migrate-<phase>`, distinct from the workload's `app: <service>`, so the Service selector never routes traffic to a migration pod.

The image must contain `alembic.ini` and `migrations/` so the same image SHA serves the app and both migration phases.

## Keep Environment Configuration Complete

Use `eu-central-1` consistently in GitHub variables, resource ARNs, and `kms:ViaService` conditions.

Use these path conventions:

```text
/ticketmaster/<env>/<key>
/ticketmaster/<service>/<env>/<key>
```

Store non-secret configuration in SSM and sensitive values in Secrets Manager. Backend secrets currently include `POSTGRES_DB_URL`, `REDIS_URL`, `SECRET`, and `SENTRY_DSN`.

In CloudFormation `ValueFrom` — no template in the repo uses this any more; the Lambda's `lambda.yaml` resolves its one KMS ARN via SSM's `{{resolve:ssm:...}}` instead, which has no ARN-suffix quirk. An ExternalSecret's `remoteRef.key` uses the plain secret/parameter name instead — no ARN involved.

`ticketmaster` consumes fourteen values and `frontend` consumes four; the ExternalSecret/ClusterSecretStore plumbing is identical across both and is the reference for every service that follows:

- `ticketmaster`: `POSTGRES_DB_URL`, `REDIS_URL`, `SECRET`, `SENTRY_DSN` from Secrets Manager `ticketmaster/ticketmaster/test-eu/*`; `ENVIRONMENT`, `SENTRY_SEND_PII`, `SENTRY_TRACES_SAMPLE_RATE`, `AWS_REGION`, `JWT_AUDIENCE`, `LAMBDA_JWT_KMS_KEY_ARN`, `LAMBDA_JWT_ISSUER`, `ADMIN_JWT_KMS_KEY_ARN`, `ADMIN_JWT_ISSUER`, `COGNITO_AUDIENCE` from SSM `/ticketmaster/ticketmaster/test-eu/*`. `AWS_REGION` has no other source on EKS — the ECS runtime injected it into every container automatically; here it's a plain SSM parameter routed through the ExternalSecret like everything else, so the shared migration-Job macro (which also constructs the full `Settings` object) needs no special-casing.
- `frontend`: `BACKEND_URL`, `COGNITO_USER_POOL_ID`, `COGNITO_USER_POOL_CLIENT_ID`, `COGNITO_DOMAIN`, all from SSM `/ticketmaster/frontend/test-eu/*`. `BACKEND_URL` is the in-cluster address of the `ticketmaster` Service (`http://ticketmaster`, no trailing slash — nginx's `proxy_pass ${BACKEND_URL};` forwards `/api/...` verbatim; the backend serves it natively), not an external URL; it is envsubst'd into nginx's `default.conf` by the stock nginx entrypoint at container start. The Cognito three are envsubst'd into a static `config.js` the SPA loads at runtime by a custom `/docker-entrypoint.d/30-render-config.sh` script.
- Each service's own `ExternalSecret` reads all of its keys — `spec.data[].sourceRef.storeRef` names a store per key (`aws-secret-store-secrets-manager`, `aws-secret-store-parameter-store`) — and writes one Kubernetes `Secret` named after the service, which its Deployment (and, for the backend, its two migration Jobs) consume with `envFrom`.
- **Two `ClusterSecretStore`s are required, not a style choice — and they are shared, not per-service.** A store holds one `spec.provider`, and the AWS provider's `service` is a scalar: `SecretsManager` or `ParameterStore`, so one store per provider is the minimum regardless of how many services exist. `aws-secret-store-secrets-manager` and `aws-secret-store-parameter-store` live under `templates/infra/external-secrets/` and are provider-scoped, not service-scoped — every service's `ExternalSecret` points at the same two stores. Neither sets `spec.conditions` to restrict which namespace may use it — only `default` exists — and `eso`'s IAM policy is account-wide read (see below), so a namespace condition would harden against nothing real. Each store's `auth.jwt.serviceAccountRef.namespace` is required, though — that field is mandatory for a `ClusterSecretStore` per ESO's docs, unlike a namespaced `SecretStore`.
- **Auth is IRSA and cannot be Pod Identity.** Both stores use `auth.jwt.serviceAccountRef` → the chart's shared `eso` ServiceAccount; ESO mints a token for that SA and calls `sts:AssumeRoleWithWebIdentity`. ESO cannot impersonate a Pod-Identity-bound service account. This is why `eso` and a workload's own AWS identity are necessarily two different mechanisms — see the `ticketmaster` bullet below.
- **One shared ServiceAccount, one IAM role, deliberately account-wide, deliberately not split per service.** `eso`'s IAM role (`ticketmaster-test-eu-eso`) holds the AWS managed policies `AmazonSSMReadOnlyAccess` and `AWSSecretsManagerClientReadOnlyAccess` — every SSM parameter and Secrets Manager secret in the account, not scoped to per-service ARN prefixes. This was a deliberate choice when `ticketmaster` was added as the second service consuming `eso`: a single shared, service-agnostic controller identity was preferred over per-service IAM scoping or a chained per-service role. Do not narrow this to per-service ARNs and do not create a second ESO ServiceAccount/role per service — that reintroduces the isolation `eso` was designed to avoid.
- The `frontend` pod does not set `serviceAccountName` — it runs as the namespace's `default` SA. It makes no AWS calls, so giving it its own ServiceAccount would be unused plumbing.
- **`ticketmaster` does make AWS calls at runtime** (`kms:GetPublicKey` on its two JWT signing keys, `cognito-idp:AdminDeleteUser`), so it runs under its own ServiceAccount, bound to an IAM role via **EKS Pod Identity**. That ServiceAccount lives at `templates/infra/services/ticketmaster/service-account.yaml`, beside the service's ExternalSecret rather than beside its workload: it is AWS-identity wiring, so it follows the same infra-tree convention (and the same `-10` wave, so the SA exists before the Deployment that references it) — a *different* mechanism from `eso`'s IRSA, deliberately: Pod Identity associations (`aws eks create-pod-identity-association`) are the more direct fit for a workload's own AWS access, while ESO specifically requires IRSA. The ticketmaster ServiceAccount carries no `eks.amazonaws.com/role-arn` annotation (that's IRSA-only); Pod Identity binds by association, not by SA annotation. Do not let a workload pod use the `eso` ServiceAccount as its own identity, and do not add an IRSA role-arn annotation to a Pod-Identity-bound ServiceAccount.
- The `ExternalSecret` carries `force-sync: {{ .Values.commitSha }}`, which makes every deploy bump `resourceVersion` so ESO re-reads AWS. Never replace it with a `kubectl annotate` step in CI.
- `Settings` subclasses `libs.settings.BaseAppSettings` (and, for `ticketmaster`, several more mixins), so a missing required value fails at import and the pod — or a migration Job — never becomes Ready/Complete. That is intentional.

Adding a backend service means: its own `ExternalSecret` under `templates/infra/services/<service>/`, referencing the existing shared `aws-secret-store-*` ClusterSecretStores — not new stores, and not a new ESO ServiceAccount. If the service makes its own AWS calls, give it its own workload ServiceAccount bound via EKS Pod Identity (never via the `eso` ServiceAccount). `frontend` is the one exception to the `infra/services/<service>/` path: since it isn't a peer of `services/<service>/` in the template tree (it's `templates/frontend/`, not `templates/services/frontend/`), its ExternalSecret lives at `templates/infra/frontend/` instead — same convention (infra tree mirrors the top-level split), different top-level key.

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
cfn-lint src/lambdas/cognito_pre_signup/lambda.yaml
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

Read the Ingress's `status.loadBalancer.ingress[0].hostname` before probing `/readiness-check`. Chart endpoints are hyphenated (`/health-check`, `/readiness-check`) for `ticketmaster`; `frontend`'s nginx exposes only `/readiness-check` (no separate `/health-check` — a static file server has no meaningful liveness/readiness distinction), used for both its liveness and readiness probes and as the shared Ingress's ALB healthcheck-path.

`Pending` pods on a cold cluster are usually Auto Mode still provisioning a node, not a scheduling failure. Check `kubectl get nodes` before diagnosing further.

## Treat Teardown as Destructive

`just test-stand-down` and `just test-stand-up` (`deploy/_scripts/test-stand-{down,up}.sh`) fully delete and recreate the `test-eu` EKS stand — the user's opt-in way to stop paying for an idle cluster between test sessions. `test-stand-down` suspends Argo auto-sync, deletes the Ingress (waiting for the ALB controller's finalizer to actually remove the ALB), deletes the cluster's IAM OIDC provider, then deletes the EKS cluster itself — nodes, EBS volumes, access entries, and the Pod Identity association go with it. `test-stand-up` recreates the cluster from the config recorded in the script, re-creates the OIDC provider and rewires the `ticketmaster-test-eu-eso` IRSA trust policy to it (the issuer changes on every recreate), recreates the Pod Identity association, reinstalls the External Secrets Operator and Argo CD, and bootstraps the Application by rendering the chart's `templates/argocd/application.yaml` locally (`helm template --show-only ... | kubectl apply`) — Argo then restores the whole app from `env/test-eu` with no CI run needed, and from that point the Application manages its own spec from the rendered branch. Because the ALB gets a new hostname each cycle, `test-stand-up` also refreshes it in the `TICKETMASTER_API_URL` SSM parameter and the Cognito pre-signup Lambda's environment.

Kept across a down/up cycle (not billed meaningfully, or hold data): IAM roles, KMS keys, Secrets Manager secrets, other SSM parameters, the Cognito user pool, ECR images, the Cognito pre-signup Lambda's CloudFormation stack, and Postgres/Redis (external to this account).

These recipes are user-invoked only — never run `just test-stand-down` or `just test-stand-up` on your own initiative, and never delete AWS resources, CloudFormation stacks, ECR repositories, or the Argo CD Application by any other means without the user explicitly asking. Deleting an Application with `prune: true` deletes every resource it tracks. For a teardown request beyond what these two recipes cover, produce the ordered console/CLI steps and let the user execute them.

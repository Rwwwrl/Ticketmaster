---
name: deployment
description: Work safely with Ticketmaster deployment and AWS infrastructure. Use for test releases, GitHub Actions, ECR, CodeArtifact, Helm template, rendered manifests, Argo CD, GitOps sync, EKS, kubectl, CloudFormation, Lambda, SSM, Secrets Manager, IAM, KMS, deployment diagnosis, or teardown.
---

# Ticketmaster Deployment

Use the repository workflows and templates as the source of truth. The only environment is `test-eu` in `eu-central-1`; never infer or invent production infrastructure.

Delivery to the cluster is GitOps: **Argo CD is the only writer to the cluster**, and git is the only source of truth for what it writes. CI never touches Kubernetes. Only `hello_world` and the Cognito PreSignUp Lambda are deployed today. `ticketmaster` and `frontend` still have code, Dockerfiles and CloudFormation templates, but **no active deployment** — their templates are the record of what the Kubernetes port must reproduce.

## Locate Deployment Code

- `.github/workflows/on-push-test.yaml`: deployment trigger and orchestration
- `.github/workflows/called-publish-python-package.yaml`: shared library publication to CodeArtifact
- `.github/workflows/called-publish-docker-images.yaml`: service image build and ECR push
- `.github/workflows/called-publish-env-manifests.yaml`: render the chart and commit to the env branch
- `.github/actions/render-manifests/action.yaml`: the one place the render is defined, shared by deploy and PR validation
- `.github/workflows/called-deploy-lambda.yaml`: Cognito PreSignUp Lambda deployment
- `.github/workflows/on-pull-request.yaml`: validation gates
- `deploy/chart/`: the single Helm chart — `templates/infra/` (`external-secrets/` with the ServiceAccount and the two shared ClusterSecretStores, `ingress/` with the IngressClass, `services/hello-world/` with its ExternalSecret) and `templates/services/hello-world/http/` (workload + Ingress), `values.yaml` (defaults) and `values.test.yaml` (test-eu)
- `env/test-eu` branch: the rendered plain-YAML manifests Argo CD applies. Machine-written by CI only — never commit to it by hand
- Argo CD Application `application-test-eu` in namespace `argocd` (created in the UI, not in this repo)
- `src/lambdas/cognito_pre_signup/lambda.yaml`: Lambda infrastructure
- `src/ticketmaster/{Dockerfile,service.yaml,migration.yaml}`, `frontend/{Dockerfile,service.yaml}`: dormant, pending the Kubernetes port

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

**`directory.recurse: true` is mandatory.** Manifests live in nested `infra/` and `services/` directories. Recurse off plus prune on makes desired state empty and deletes everything the Application tracks, including the Ingress (and the ALB). Do not turn recurse off. Do not recreate this Application from scratch unless the user explicitly asks; editing it in the Argo UI YAML pane is spec-only — do not wrap a second `apiVersion`/`kind`/`spec`.

The UI is port-forward only. There is no Ingress, LoadBalancer, or SSO for Argo:

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443
# https://localhost:8080  (self-signed cert; user admin)
```

The ordering guarantee is structural: **Argo watches a ref only CI writes, and CI writes it only after the images are pushed.** Never restore a `helm upgrade` or `kubectl apply` step in CI — two writers of the same resources is the failure this design removes. Helm is a render tool in CI, not a cluster release manager. `helm status` / `helm rollback` return nothing. Rollback means reverting the commit on `env/test-eu`, or re-running the pipeline on the previous source commit.

**Sync waves are two values only, defaulting to `0` in `values.yaml` and overridden per environment in `values.test.yaml`.** `infra.meta.argocd.syncWave` defaults to `0` and is set to `-10` for test-eu; `services.helloWorld.meta.argocd.syncWave` stays `0` in both files. Every template in that directory reads `argocd.argoproj.io/sync-wave: {{ .Values.<tier>.meta.argocd.syncWave | quote }}` rather than hardcoding the string. The wave is a property of the top-level template directory — everything under `templates/infra/**` (including each service's ExternalSecret, which lives at `infra/services/<service>/` rather than beside its workload) reads the infra wave; everything under `templates/services/<service>/**` reads that service's wave. Do not invent per-resource waves, and change the number in `values.yaml`/`values.test.yaml`, not in individual templates. `-5` is reserved for the RabbitMQ topology Job when it lands. Waves make the sync multi-step, so a Degraded resource now fails the operation and auto-sync will not retry the same commit SHA; the Application's `retry` block covers transient cases, beyond that it needs a manual Sync.

**`values.yaml` mirrors the template tree, with one exception: `meta`.** A tier's keys generally match its template subdirectories one-to-one (e.g. `infra.externalSecrets`, `infra.services`), but anything that is not a folder — the sync wave, the shared AWS region — lives under that tier's `meta` key instead (`infra.meta.argocd.syncWave`, `infra.meta.region`, `services.helloWorld.meta.argocd.syncWave`). Keep new values inside this convention rather than adding tier-level siblings that aren't folders.

**Do not add `argocd.argoproj.io/sync-options: Prune=false` to the `ExternalSecret`.** Pruning it is recoverable — the value lives in AWS, so reverting the commit brings the `Secret` back. `Prune=false` is reserved for resources holding state the cluster is the only copy of, such as a RabbitMQ `Queue`.

**`commitSha` is chart-level, not per-service.** Every image in this repo is tagged with the same commit SHA, so the chart declares one `commitSha` value and each service template reads it — adding a service never touches CI. It is `required` in the template, so a render that loses the `--set` fails loudly instead of emitting a tag no one pushed. Do not reintroduce a per-service `image.tag` value or a default tag in `values.yaml`.

The action deliberately holds **no** manifest allow-list and no post-render assertions: removing a template is how you remove a resource, and CI is the wrong place to encode the shape of the chart. What catches failure is `helm template` itself under `set -euo pipefail`, plus kubeconform on PRs.

Never add a timestamp or run-number banner to the rendered output — the no-op "nothing to commit" path depends on the render being byte-deterministic.

**Accepted risk:** the Application prunes, so a render that produced no manifests would be a valid commit that wipes the cluster. Nothing in the chart sits behind a conditional today, so it cannot silently shrink. If you ever add `{{- if .Values.x.enabled }}` around a template, revisit that.

CI goes green at `git push`, before the deploy lands; there is no `argocd app wait` gate. The cluster is EKS Auto Mode and scales from zero, so a cold deploy pays node provisioning plus image pull before any pod is Ready — check Argo, not the workflow, to know a deploy finished.

Service images must not copy a `poetry.lock`. Service `pyproject.toml` files declare a published `ticketmaster-libs` version; the build resolves it from CodeArtifact using `--build-arg CODEARTIFACT_INDEX_URL` and `--secret id=codeartifact_token`. Never bake the token into a layer.

**Dormant rule, restore with the backend port:** database migrations run expand → rollout → contract. Never reorder or collapse that sequence, stop after an expand failure, and do not run contract after a failed rollout. The backend image must contain `alembic.ini` and `migrations/` so the same image SHA serves the app and both migration phases. There is no migration step in the pipeline today.

## Keep Environment Configuration Complete

Use `eu-central-1` consistently in GitHub variables, resource ARNs, and `kms:ViaService` conditions.

Use these path conventions:

```text
/ticketmaster/<env>/<key>
/ticketmaster/<service>/<env>/<key>
```

Store non-secret configuration in SSM and sensitive values in Secrets Manager. Backend secrets currently include `POSTGRES_DB_URL`, `REDIS_URL`, `SECRET`, and `SENTRY_DSN`.

In CloudFormation `ValueFrom`, use the Secrets Manager ARN without the generated `-XxXxXx` suffix. Match the runtime secret in IAM with an appropriate wildcard.

`hello_world` consumes exactly two values, and the plumbing is the reference for every service that follows:

- `SECRET` from Secrets Manager `ticketmaster/hello-world/test-eu/SECRET`, `ENVIRONMENT` from SSM `/ticketmaster/hello-world/test-eu/ENVIRONMENT`.
- One `ExternalSecret` reads both — `spec.data[].sourceRef.storeRef` names a store per key (`aws-secret-store-secrets-manager`, `aws-secret-store-parameter-store`) — and writes one Kubernetes `Secret` named `hello-world`, which the Deployment consumes with `envFrom`.
- **Two `ClusterSecretStore`s are required, not a style choice — and they are shared, not per-service.** A store holds one `spec.provider`, and the AWS provider's `service` is a scalar: `SecretsManager` or `ParameterStore`, so one store per provider is the minimum regardless of how many services exist. `aws-secret-store-secrets-manager` and `aws-secret-store-parameter-store` live under `templates/infra/external-secrets/` and are provider-scoped, not hello-world-scoped — every service's `ExternalSecret` points at the same two stores. Neither sets `spec.conditions` to restrict which namespace may use it — only `default` exists, and IAM already scopes `eso` to hello-world's ARNs regardless of the caller's namespace, so it would harden against nothing real. Each store's `auth.jwt.serviceAccountRef.namespace` is required, though — that field is mandatory for a `ClusterSecretStore` per ESO's docs, unlike a namespaced `SecretStore`.
- **Auth is IRSA and cannot be Pod Identity.** Both stores use `auth.jwt.serviceAccountRef` → the chart's shared `eso` ServiceAccount; ESO mints a token for that SA and calls `sts:AssumeRoleWithWebIdentity`. ESO cannot impersonate a Pod-Identity-bound service account.
- **One shared ServiceAccount, one IAM role, direct permissions — deliberately, for now.** `eso`'s own policy holds `secretsmanager:GetSecretValue` / `ssm:GetParameter` scoped to hello-world's ARNs. There is no per-service chained role: with one service it would add indirection for nothing. When a second service arrives, either widen `eso`'s policy or split it into an assume-only base role plus one chained role per service — `docs/aws_setup.md` section 14 documents both. The IAM role, its trust policy and the cluster's IAM OIDC provider are manual AWS work, and none of it is in this repo.
- The `hello_world` pod itself does not set `serviceAccountName` — it runs as the namespace's `default` SA. It makes no AWS calls, so giving it its own ServiceAccount would be unused plumbing.
- The `ExternalSecret` carries `force-sync: {{ .Values.commitSha }}`, which makes every deploy bump `resourceVersion` so ESO re-reads AWS. Never replace it with a `kubectl annotate` step in CI.
- `Settings` subclasses `libs.settings.BaseAppSettings`, which requires both fields, so a missing value fails at import and the pod never becomes Ready. That is intentional. `GET /hello-world` returns a SHA-256 fingerprint of the secret, never the value.

Adding a service means: its own `ExternalSecret` under `templates/infra/services/<service>/`, referencing the existing shared `aws-secret-store-*` ClusterSecretStores — not new stores, and not a new ServiceAccount. Widening `eso`'s policy with the new service's ARNs is fine short-term; if that union grows uncomfortable, split `eso` into an assume-only base role plus a chained per-service role (`docs/aws_setup.md` section 14) rather than creating a new ServiceAccount. Do not let a workload pod use the `eso` ServiceAccount as its own identity.

Whenever a required setting is added or renamed, update the chart or CloudFormation template that injects it, update test environment configuration, and ensure the value exists in SSM or Secrets Manager for `test-eu`.

Preserve least-privilege roles. The Lambda role signs with its specific KMS key.

Expected GitHub environment variables: `AWS_REGION`, `AWS_ACCOUNT_ID`, `DEPLOYER_TO_AWS_ROLE_ARN`, `CODEARTIFACT_DOMAIN`, `CODEARTIFACT_REPOSITORY`, and `EKS_CLUSTER_NAME`.

## Prepare a Deployment Change

Before an explicitly requested deploy:

1. Inspect the branch and exact diff.
2. Confirm the target is `test-eu` in `eu-central-1`.
3. Bump package versions for changes under `src/libs/`, `src/ticketmaster/`, or `src/hello_world/`. If the shared library version is unchanged, publication may skip it and services can install old code.
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
cfn-lint src/*/service.yaml src/*/migration.yaml frontend/service.yaml
helm template ticketmaster ./deploy/chart \
  -f ./deploy/chart/values.test.yaml \
  --set commitSha=dummy --output-dir /tmp/rendered
kubeconform -strict -summary -schema-location default /tmp/rendered
```

Also lint `src/lambdas/cognito_pre_signup/lambda.yaml` when Lambda infrastructure changes.

## Diagnose Without Mutating

For explanation, status, review, or diagnosis requests, remain read-only. Inspect workflow runs, failed logs, pod status, and readiness without pushing, rerunning, deploying, or changing AWS or cluster resources.

Useful read-only commands include:

```bash
gh run list --workflow on-push-test.yaml --branch <test-branch>
gh run view <run-id> --log-failed
aws eks update-kubeconfig --name ticketmaster-test-eu --region eu-central-1
kubectl get pods,svc,ingress
kubectl describe pod <pod>
kubectl logs deploy/hello-world
kubectl -n argocd port-forward svc/argocd-server 8080:443
argocd app get application-test-eu
argocd app history application-test-eu
git log --oneline origin/env/test-eu
aws cloudformation describe-stack-events --stack-name ticketmaster-cognito-pre-signup-test-eu --region eu-central-1
```

There is no Helm release any more, so `helm status`, `helm history` and `helm rollback` all return nothing. Rollback means reverting the commit on `env/test-eu`, or re-running the pipeline on the previous source commit. Argo is reachable only through `kubectl port-forward` today. `selfHeal` reverts a manual `kubectl edit` of tracked resources; that is intended.

Read the Ingress's `status.loadBalancer.ingress[0].hostname` before probing `/readiness-check`. Chart endpoints are hyphenated (`/health-check`, `/readiness-check`); the dormant CloudFormation templates use `/readiness_check`.

`Pending` pods on a cold cluster are usually Auto Mode still provisioning a node, not a scheduling failure. Check `kubectl get nodes` before diagnosing further.

## Treat Teardown as Destructive

There is no teardown recipe in the `justfile`; teardown is a manual AWS Console procedure performed by the user. Never delete AWS resources, CloudFormation stacks, ECR repositories, or the Argo CD Application on your own initiative. Deleting an Application with `prune: true` deletes every resource it tracks. For an explicit teardown request, produce the ordered console steps and let the user execute them.

---
name: deployment
description: Work safely with Ticketmaster deployment and AWS infrastructure. Use for test releases, GitHub Actions, ECR, CodeArtifact, Helm, EKS, kubectl, CloudFormation, Lambda, SSM, Secrets Manager, IAM, KMS, deployment diagnosis, or teardown.
---

# Ticketmaster Deployment

Use the repository workflows and templates as the source of truth. The only environment is `test-eu` in `eu-central-1`; never infer or invent production infrastructure.

Deployment is mid-migration from ECS to Kubernetes. Only `hello_world` and the Cognito PreSignUp Lambda are deployed today. `ticketmaster` and `frontend` still have code, Dockerfiles and CloudFormation templates, but **no active deployment** — their templates are the record of what the Kubernetes port must reproduce.

## Locate Deployment Code

- `.github/workflows/on-push-test.yaml`: deployment trigger and orchestration
- `.github/workflows/called-publish-python-package.yaml`: shared library publication to CodeArtifact
- `.github/workflows/called-publish-docker-images.yaml`: service image build and ECR push
- `.github/workflows/called-helm-upgrade.yaml`: Helm release on EKS
- `.github/workflows/called-deploy-lambda.yaml`: Cognito PreSignUp Lambda deployment
- `.github/workflows/on-pull-request.yaml`: validation gates
- `deploy/infra/`: infrastructure Helm chart (IngressClass today)
- `deploy/application/`: application Helm chart, `values.yaml` (defaults) and `values.test.yaml` (test-eu)
- `src/lambdas/cognito_pre_signup/lambda.yaml`: Lambda infrastructure
- `src/ticketmaster/{Dockerfile,service.yaml,migration.yaml}`, `frontend/{Dockerfile,service.yaml}`: dormant, pending the Kubernetes port

## Preserve the Release Flow

A push to `test/**` triggers the test deployment. It uses GitHub OIDC, the `deploy-test-eu` concurrency group, and does not cancel an in-progress deployment.

The workflow:

1. `publish-libs` — publish `src/libs` to CodeArtifact.
2. `publish-services-docker-images` — build each service image tagged with the Git SHA and push to ECR. Needs `publish-libs`: the Docker build installs `ticketmaster-libs` from CodeArtifact and must not race the publish.
3. `helm-upgrade-infra` — `helm upgrade --install infra ./deploy/infra`. No image tag. Runs in parallel with publish.
4. `helm-upgrade-application` — needs images and infra. `helm upgrade --install application ./deploy/application` into the default namespace, with `--set helloWorld.image.tag=<sha>`.

`deploy-cognito-pre-signup-lambda` runs in parallel; it has no `ticketmaster-libs` dependency.

Keep `--wait` and a timeout of at least `10m`. The cluster is EKS Auto Mode and scales from zero, so a cold deploy pays Karpenter node provisioning plus image pull before any pod is ready.

Service images must not copy a `poetry.lock`. Service `pyproject.toml` files declare a published `ticketmaster-libs` version; the build resolves it from CodeArtifact using `--build-arg CODEARTIFACT_INDEX_URL` and `--mount=type=secret,id=codeartifact_token`. Never bake the token into a layer.

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

`hello_world` needs **zero configuration**. The chart injects no env vars at all — there is no `env:` block, no `ConfigMap`, no Kubernetes `Secret`, no External Secrets Operator, and the pod makes no AWS calls. It proves the `ticketmaster-libs` dependency by inheriting `BaseResponseSchema` from `libs.fastapi_ext.schemas.base_schemas`, which needs no settings. Do not add configuration plumbing without an explicit request.

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
cfn-lint src/ticketmaster/service.yaml src/ticketmaster/migration.yaml frontend/service.yaml
helm template infra ./deploy/infra | kubeconform -strict -summary -schema-location default
helm template application ./deploy/application \
  -f ./deploy/application/values.test.yaml \
  --set helloWorld.image.tag=dummy | kubeconform -strict -summary -schema-location default
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
helm status infra
helm status application
aws cloudformation describe-stack-events --stack-name ticketmaster-cognito-pre-signup-test-eu --region eu-central-1
```

Read the Ingress's `status.loadBalancer.ingress[0].hostname` before probing `/readiness-check`. Note the chart's endpoints are hyphenated (`/health-check`, `/readiness-check`); the dormant ECS templates use `/readiness_check`.

`Pending` pods on a cold cluster are usually Auto Mode still provisioning a node, not a scheduling failure. Check `kubectl get nodes` before diagnosing further.

## Treat Teardown as Destructive

There is no teardown recipe in the `justfile`; teardown is a manual AWS Console procedure performed by the user. Never delete AWS resources, CloudFormation stacks, ECR repositories, or Helm releases on your own initiative. For an explicit teardown request, produce the ordered console steps and let the user execute them.

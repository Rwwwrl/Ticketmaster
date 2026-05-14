---
name: cicd
description: Mental model and conventions for ticketmaster's CI/CD pipeline — GitHub Actions OIDC → CodeArtifact (for libs) and ECR → CloudFormation → ECS Express Mode (for services), plus alembic expand/contract migrations as one-shot Fargate tasks. Use whenever the user touches anything under `.github/workflows/`, `.github/actions/`, a `service.yaml` or `migration.yaml` CloudFormation template, the `Dockerfile`, or asks about CI checks, deploys, ECR/ECS/CloudFormation/OIDC, secrets injection, library publishing, or migrations in this repo — even if they don't say "deploy" or "CI" explicitly. Trigger phrases include "cicd", "ci/cd", "deploy", "deployment", "pipeline", "workflow", "GitHub Actions", "ECR", "ECS", "CloudFormation", "service.yaml", "migration.yaml", "OIDC", "role ARN", "stack", "new service", "aws-down", "task definition", "secrets manager", "ssm parameter", "codeartifact", "alembic", "expand contract", "lint", "ruff", "pytest", "cfn-lint".
---

# Ticketmaster CI/CD

This skill is the canonical mental model of how code goes from a push to a running container in AWS. Read it before editing anything under `.github/`, any `*.yaml` CloudFormation template, the `Dockerfile`, or the `justfile` AWS recipes.

## The One-Liner

**A trigger workflow says *what + when*; reusable workflows say *how*; each `service.yaml` says *what it looks like running*; OIDC + passed-in role ARNs are how all of this happens without a single long-lived credential.**

## The Two Halves

The pipeline has a **CI half** (runs on pull requests, gates merges) and a **CD half** (runs on pushes to env-trigger branches, ships to AWS). They share nothing except OIDC auth.

```
PR opened ──► on-pull-request.yaml ──► [check_versions, validate_cloudformation, lint_and_test]   (CI: gate the merge)

push test/** ──► on-push-test.yaml ──► publish-libs ──► deploy-ticketmaster                       (CD: ship to AWS)
                                          │                  │
                                          ▼                  ▼
                                   CodeArtifact         ECR + CloudFormation + ECS
```

Trigger workflows are dumb on purpose — they pick the env, list the services, call reusable workflows. All real logic lives in the reusable workflows.

## Repo Layout

```
.github/
  workflows/
    on-pull-request.yaml                    # CI: PR gate
    on-push-test.yaml                       # CD: push test/** → test-eu
    called-publish-python-package.yaml      # reusable: poetry build → CodeArtifact
    called-deploy-container-service.yaml    # reusable: docker → ECR → CFN → ECS + migrations
  actions/
    run-ecs-migration/action.yaml           # composite: alembic upgrade as a one-shot Fargate task

src/
  libs/                                     # ticketmaster-libs — published to CodeArtifact
    pyproject.toml
  ticketmaster/                             # the FastAPI service
    pyproject.toml
    Dockerfile
    service.yaml                            # ECS Express service stack
    migration.yaml                          # one-shot migration task-def stack
    ticketmaster/                           # actual Python package
    migrations/                             # alembic revisions
    alembic.ini

justfile                                    # local dev + `aws-down` teardown
```

## CI: `on-pull-request.yaml`

Triggers on PRs against `main`. Three parallel jobs — every one must pass to merge.

### `check_versions`
If a PR touches `src/libs/**` or `src/ticketmaster/**`, the corresponding `pyproject.toml` `version` must be bumped. Enforced in CI rather than by convention because forgetting a bump means CodeArtifact silently keeps serving the old wheel — services deploy stale code.

### `validate_cloudformation`
Runs `cfn-lint` against every `service.yaml` and `migration.yaml`. Catches typos in `!Ref`, missing `Parameters` blocks, malformed ARNs *before* CloudFormation refuses them mid-deploy. Cheap, fast, no AWS creds needed.

### `lint_and_test`
- Spins up Postgres 17 as a service container on port `15432` (matches `env.dev.yaml` so tests can hit it the same way local dev does).
- Poetry `1.8.3` (pinned — `2.x` changes lockfile semantics).
- `ruff check .` + `ruff format --check .` (line length 120, see `AGENTS.md`).
- `pytest --cov` with **75% minimum coverage** for both `src/libs/libs` and `src/ticketmaster/ticketmaster`.

If you add a new deployable Python package under `src/`, you'll need to extend this job to lint/test it too.

## CD: From Push to Running Container

### Step 0: branch trigger
`on-push-test.yaml` fires on pushes matching `test/**`. The branch name *is* the deploy intent — there's no manual approve step. Naming convention is `test/<feature>` for routine work.

The trigger workflow does two things, **in order** (`needs:`):

```
publish-libs   ──►   deploy-ticketmaster
```

Libs must be published **first** because the service's `pyproject.toml` pins `ticketmaster-libs ^0.X.Y`, and the service Docker build pulls from CodeArtifact. Reverse the order and the build fails resolving deps.

### Step 1: publish libs → CodeArtifact (`called-publish-python-package.yaml`)

CodeArtifact is AWS's private Python package registry — the AWS analogue of GCP Artifact Registry's Python repos.

```
OIDC → assume DEPLOYER role
     → aws codeartifact get-authorization-token
     → poetry config repositories.codeartifact <endpoint>
     → poetry config http-basic.codeartifact aws <token>
     → poetry build && poetry publish --repository codeartifact
```

Tolerates "version already exists" non-fatally — re-running a deploy of the same SHA shouldn't fail just because the wheel is already there. That's also why `check_versions` lives in CI: the bump is enforced *before* the merge, not when the publish would 409.

### Step 2: deploy service (`called-deploy-container-service.yaml`)

This is the workflow that does the actual ship. Inputs: `(environment, service_name, service_path, run_migrations)`. Steps:

1. **OIDC → assume `DEPLOYER_TO_AWS_ROLE_ARN`.** Job needs `permissions: id-token: write`. If you see *"Could not assume role"*, that line is missing or the role's trust policy doesn't match `repo:<owner>/<repo>:*`.
2. **ECR login.** One repo per service, repo name == `service_name`.
3. **Docker build + push.** Tag is `${{ github.sha }}` — never `latest`. Build receives a CodeArtifact token via Docker BuildKit secret mount so the image can `poetry install` from the private registry without baking the token into a layer.
4. **(if `run_migrations`) deploy migration stack** — `aws cloudformation deploy --stack-name <service>-<env>-migrate --template-file migration.yaml`. This stack only owns a `TaskDefinition` + `LogGroup`; no running containers.
5. **(if `run_migrations`) run expand migrations** — `run-ecs-migration` composite action. Command: `poetry run alembic upgrade expand@head`.
6. **Deploy service stack** — `aws cloudformation deploy --stack-name <service>-<env> --template-file service.yaml`. Passes the SHA as `ImageTag`. ECS Express Mode rolls the running tasks.
7. **(if `run_migrations`) run contract migrations** — `poetry run alembic upgrade contract@head`. Removes the columns/tables old code depended on, now that no old code is running.

`--no-fail-on-empty-changeset` on both deploys: code-only changes (new SHA, same template) shouldn't fail the deploy.

Total budget: 25-minute job timeout, with 120s task-start + 180s task-stop on migrations (Fargate cold start + image pull + secrets fetch is ~30–60s; expand migrations with backfill can take a while).

## Expand / Contract Migrations

This pattern is the load-bearing reason there are two migration steps:

```
old code running ──► [EXPAND]    ──► old + new code can both run
                                       (deploy new code; old tasks drain)
                  ──► [CONTRACT]  ──► only new code can run
```

Expand: additive only — new columns nullable, new tables, new indexes. Old code is untouched and keeps working. Contract: drop the old columns/tables. **Never put a destructive migration in expand or you'll break the still-running old tasks during the rollout.**

Alembic supports this with two branch heads (`expand` and `contract`). The composite action `.github/actions/run-ecs-migration/action.yaml` runs whatever command you give it inside the migration task definition, so the workflow calls it twice — once around the deploy, once after.

### `run-ecs-migration` composite action

Inputs: `(stack_name, command)`. What it does:

1. Reads `MigrationTaskDefinitionArn` from the migration stack's outputs.
2. Discovers default VPC + subnets + default SG (no networking config in the workflow — the action figures it out).
3. Splits `command` on whitespace into argv, hands it to `geekcell/github-action-aws-ecs-run-task@v5.0.1`.
4. Runs as a Fargate task; streams logs; exits non-zero if the task fails.

The `migrate` container name is hardcoded — every `migration.yaml` must define its container as `Name: migrate`.

## The Per-Service Contract

Every `src/<service>/service.yaml` **must** accept these four parameters — the reusable workflow passes them unconditionally:

| Parameter                | Source                              | Why                                                |
| ------------------------ | ----------------------------------- | -------------------------------------------------- |
| `ImageTag`               | `github.sha`                        | Immutable image pointer for this deploy            |
| `Environment`            | workflow input                      | Suffix in resource names; `AllowedValues` enforced |
| `ExecutionRoleArn`       | `vars.ECS_EXECUTION_ROLE_ARN`       | ECS agent uses this to pull image + fetch secrets  |
| `InfrastructureRoleArn`  | `vars.ECS_INFRASTRUCTURE_ROLE_ARN`  | ECS uses this to manage ALB/TGs/SGs in Express Mode |

Every `src/<service>/migration.yaml` accepts three: `ImageTag`, `Environment`, `ExecutionRoleArn` (no infra role — migrations don't need an ALB).

The two role ARNs are passed in (not hardcoded in templates) so the same template works across accounts/environments without editing. **If you add a template and omit one of these parameters, the deploy fails.**

The service template uses `AWS::ECS::ExpressGatewayService` — not classic `AWS::ECS::Service` — because Express Mode manages the ALB/target groups/SGs for us via `InfrastructureRoleArn`. That's the whole reason we pass that role.

## Config & Secrets Injection

Services need runtime config and secrets without baking them into the image and without leaking them through CI. The ECS task definition's `Secrets:` block does this — the ECS agent fetches values at task startup and injects them as env vars before the container runs.

### The split — and why two services

Mirror the eshop2 GKE pattern, just renamed for AWS:

| eshop2 (GKE)                                       | Ticketmaster (AWS)                                                    |
| -------------------------------------------------- | --------------------------------------------------------------------- |
| ConfigMap (non-sensitive)                          | **SSM Parameter Store** (`String`, free)                              |
| GCP Secret Manager (sensitive)                     | **AWS Secrets Manager** (~$0.40/secret/month, supports rotation)      |
| `ClusterSecretStore` + Workload Identity           | IAM permission on the **task execution role**                         |
| `ExternalSecret` CR (mapping remote key → K8s key) | ECS task definition `Secrets:` block (mapping ARN → env var name)     |
| Synced K8s `Secret` object                         | *(no intermediate object — ECS agent fetches at task startup)*        |
| Pod `envFrom: secretRef` / `configMapRef`          | Container env vars, populated by ECS agent at task start              |

Use **SSM Parameter Store** for log levels, feature flags, hostnames — anything that's just config. Free for `String`/`StringList`, plain text. Use **AWS Secrets Manager** for credentials, API keys, anything needing KMS-encryption-at-rest or rotation.

Both backends are referenced from the task definition through the same `Secrets: [{Name, ValueFrom}]` block — only the ARN scheme differs (`arn:aws:ssm:…:parameter/…` vs `arn:aws:secretsmanager:…:secret:…`). ECS picks the right backend from the ARN.

### Why no intermediate object (vs `ExternalSecret`)

In Kubernetes, ExternalSecret syncs values from GCP Secret Manager into a K8s `Secret` that the pod mounts via `envFrom`. AWS skips that hop: the ECS agent reads from SSM/Secrets Manager directly at task startup using the execution role's IAM perms and injects values straight into the container env. **The mapping (env var name → AWS resource ARN) lives entirely in `service.yaml` — nothing about it touches CI.** Rotating a value in Secrets Manager doesn't change the template or trigger a redeploy.

### The pattern

```yaml
PrimaryContainer:
  Image: !Sub '${AWS::AccountId}.dkr.ecr.${AWS::Region}.amazonaws.com/ticketmaster:${ImageTag}'
  ContainerPort: 8080
  Secrets:
    - Name: ENVIRONMENT
      ValueFrom: !Sub 'arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/ticketmaster/ticketmaster/${Environment}/ENVIRONMENT'
    - Name: POSTGRES_DB_URL
      ValueFrom: !Sub 'arn:aws:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:ticketmaster/ticketmaster/${Environment}/POSTGRES_DB_URL'
```

Both `ENVIRONMENT` and `POSTGRES_DB_URL` reach the container as env vars; the app reads them via pydantic-settings (case-insensitive — they map to lowercase `environment` / `postgres_db_url` fields in the `Settings` class).

`migration.yaml` reuses the **same** `Secrets:` block as `service.yaml`. Migrations need the same DB URL the service uses — drift between the two means the migration runs against a different database than the service.

### Why ARNs are hardcoded (no CFN parameter, no GH Actions var)

- The whole point is the env-var → AWS-resource mapping lives in the template. Promoting ARNs to CFN parameters would re-introduce config into CI, defeating the design.
- Hardcoding `test-eu` in the ARN means a future `prod-eu` template needs different literals. Acceptable cost; per-env templates may show up anyway as services diverge.
- (Note: in this repo, ARNs use the partial form without the `-XxXxXx` random suffix — ECS accepts the partial ARN and IAM matches via wildcard at runtime. If a template fails with `unable to pull secrets`, the suffix is rarely the issue here; check IAM scope first.)

### IAM: extend the *execution* role, not the task role

The **execution** role is what the ECS agent uses to start the task (pull from ECR, write logs, fetch secrets/parameters). The **task** role is what the running app uses for its own AWS SDK calls. Secret/parameter fetching happens *before* the container starts — execution role.

One-time per AWS account, attach an inline policy to the role behind `vars.ECS_EXECUTION_ROLE_ARN`, scoped under `/ticketmaster/*` so future services share it without re-editing IAM:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Sid": "ReadSsmConfig",      "Effect": "Allow", "Action": ["ssm:GetParameters"],            "Resource": "arn:aws:ssm:*:*:parameter/ticketmaster/*"},
    {"Sid": "ReadSecretsManager", "Effect": "Allow", "Action": ["secretsmanager:GetSecretValue"],"Resource": "arn:aws:secretsmanager:*:*:secret:ticketmaster/*"},
    {"Sid": "DecryptDefaultKmsKey","Effect":"Allow", "Action": ["kms:Decrypt"],                  "Resource": "*",
      "Condition": {"StringEquals": {"kms:ViaService": ["secretsmanager.eu-central-1.amazonaws.com","ssm.eu-central-1.amazonaws.com"]}}}
  ]
}
```

`kms:Decrypt` is needed because Secrets Manager always KMS-encrypts at rest. The `kms:ViaService` condition scopes the perm to KMS calls made on behalf of those two services — can't be reused to decrypt arbitrary keys.

## Naming Conventions

Stick to these — anything that depends on naming (IAM scope, stack delete, ARN construction, `aws-down`) breaks if you drift.

| Thing                            | Format                                              | Example                                                              |
| -------------------------------- | --------------------------------------------------- | -------------------------------------------------------------------- |
| Environment                      | `<service>-<region-code>`                           | `test-eu`                                                            |
| AWS region                       | always `eu-central-1` (Frankfurt)                   |                                                                      |
| ECR repo                         | `<service_name>`                                    | `ticketmaster`                                                       |
| Service stack                    | `<service>-<env>`                                   | `ticketmaster-test-eu`                                               |
| Migration stack                  | `<service>-<env>-migrate`                           | `ticketmaster-test-eu-migrate`                                       |
| Service log group                | `/ecs/<service>-<env>`                              | `/ecs/ticketmaster-test-eu`                                          |
| Migration log group              | `/ecs/<service>-<env>-migrate`                      | `/ecs/ticketmaster-test-eu-migrate`                                  |
| SSM parameter (env-shared)       | `/ticketmaster/<env>/<key>`                         | `/ticketmaster/test-eu/migration_subnets`                            |
| SSM parameter (service-scoped)   | `/ticketmaster/<service>/<env>/<KEY>`               | `/ticketmaster/ticketmaster/test-eu/ENVIRONMENT`                     |
| Secrets Manager secret           | `ticketmaster/<service>/<env>/<KEY>` (no leading `/`) | `ticketmaster/ticketmaster/test-eu/POSTGRES_DB_URL`                  |
| Env var in container             | `<KEY>` matching pydantic-settings field (case-insensitive) | `POSTGRES_DB_URL` ↔ `postgres_db_url: str`                  |
| Image tag                        | `${{ github.sha }}` — never `latest`                |                                                                      |
| Branch trigger                   | `test/**` → `test-eu`                               | `test/add-bookings-endpoint`                                         |
| Migration container name         | `migrate` (hardcoded in composite action)           |                                                                      |
| Pinned tool versions             | Poetry `1.8.3`, Python `3.14`                       |                                                                      |

## Required GitHub Actions Variables

Set **per environment** under repo settings → Environments → `<env>` → Variables:

- `AWS_REGION` — `eu-central-1`
- `AWS_ACCOUNT_ID` — 12-digit account ID (used to build the ECR registry URL)
- `DEPLOYER_TO_AWS_ROLE_ARN` — role GH Actions assumes (ECR push + CloudFormation deploy + `iam:PassRole` on the two role ARNs below + CodeArtifact get-token + ECS RunTask)
- `ECS_EXECUTION_ROLE_ARN` — task execution role (ECR read, CloudWatch Logs write, SSM/Secrets Manager read, KMS decrypt)
- `ECS_INFRASTRUCTURE_ROLE_ARN` — ECS service role for Express Mode
- `CODEARTIFACT_DOMAIN` — CodeArtifact domain name
- `CODEARTIFACT_REPOSITORY` — CodeArtifact repository name within that domain

Setting all seven is the checklist when adding a new environment. They're **environment** variables, not repo-level, so different envs can point at different accounts.

## Recipes

### Add a config value or secret to an existing service

1. Create the SSM parameter or Secrets Manager secret in the AWS console (one-time per env).
2. Add an entry to the service's `service.yaml` **and** `migration.yaml` under `Secrets:` (keep them in sync — migrations need the same env).
3. Add the field to the app's `Settings` class (pydantic-settings) and to local `env.dev.yaml`.
4. Push. IAM is already broad enough (`/ticketmaster/*` scope) — no IAM edit needed.

### Add a new deployable service

Goal: add `src/<new-service>/` and have it deploy on push to `test/**`.

1. **Create the service directory** with a `Dockerfile` exposing port 8080 and a `/readiness_check` endpoint (current convention).
2. **Write `src/<new-service>/service.yaml`** — copy `src/ticketmaster/service.yaml` as the starting shape. Keep the four required parameters. Rename the log group, service name, container port if needed.
3. **Write `src/<new-service>/migration.yaml`** if the service has a database — copy `src/ticketmaster/migration.yaml`.
4. **Bootstrap the ECR repo** (one-time, outside CI):
   ```bash
   aws ecr create-repository --repository-name <new-service> --region eu-central-1
   ```
5. **Add a deploy job** to the relevant trigger workflow (e.g. `on-push-test.yaml`):
   ```yaml
   deploy-<new-service>:
     uses: ./.github/workflows/called-deploy-container-service.yaml
     with:
       environment: test-eu
       service_name: <new-service>
       service_path: src/<new-service>
       run_migrations: true   # if it has a DB
     secrets: inherit
   ```
6. **Extend the `lint_and_test` job** in `on-pull-request.yaml` to also lint/test the new package + extend `check_versions` paths.
7. **Push to a `test/**` branch**.

### Tear down idle test stacks

Cost control:
```bash
just aws-down env=test-eu profile=tm-test
```

Deletes both stacks (`ticketmaster-test-eu` and `ticketmaster-test-eu-migrate`) — ALB, NAT, ECS service, task defs all go. ECR repo + images stay (cheap, want them for the next deploy). Re-creating is just pushing to the trigger branch again.

## Debugging — Where to Look When It Fails

| Symptom                                                                 | Most likely cause                                                                                                            |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `Could not assume role` / OIDC error                                    | Missing `permissions: id-token: write` on the job, or trust policy doesn't match `repo:<owner>/<repo>:*`                     |
| `repository does not exist` on docker push                              | ECR repo for `service_name` was never created (one-time bootstrap)                                                           |
| CloudFormation `ROLLBACK_COMPLETE`                                      | Check **stack events in AWS console**, not just CI log — workflow only sees the deploy failure, not the *reason*             |
| `Parameter … does not exist` on deploy                                  | Reusable workflow passes 4 params; template only declares 3. Add the param block, or default it.                             |
| Deploy "succeeds" but service unhealthy                                 | `ContainerPort` doesn't match what the app listens on, or `HealthCheckPath` (currently `/readiness_check`) returns non-200   |
| `ResourceInitializationError: unable to pull secrets or registry auth`  | IAM gap on **execution** role — missing `ssm:GetParameters` / `secretsmanager:GetSecretValue` / `kms:Decrypt`               |
| App crashes at startup with pydantic `ValidationError` for a config field | Value not reaching container. Check rendered task definition in ECS console (Tasks → click task → JSON) — if `secrets` array is missing entries, `service.yaml` change didn't deploy |
| `check_versions` CI fails on PR                                         | You changed code under `src/libs/` or `src/ticketmaster/` but didn't bump that package's `pyproject.toml` `version`          |
| `cfn-lint` CI fails                                                     | Typo in `!Ref`, missing `Parameters:` entry, malformed `!Sub` ARN. Run `cfn-lint <file>` locally to reproduce.               |
| Lib publish fails with 403 / token error                                | `DEPLOYER_TO_AWS_ROLE_ARN` lacks `codeartifact:GetAuthorizationToken` or `sts:GetServiceBearerToken`                         |
| Migration task fails with `Essential container exited`                  | Look at the migration log group (`/ecs/<service>-<env>-migrate`) — usually an alembic conflict or a missing env var          |
| Service deployed new SHA but contract migration step failed             | Old tasks already drained — DB is in expanded state. Either fix the migration and re-push, or `alembic downgrade` manually.  |

When editing the reusable workflow, remember every service uses it. A change that adds a new required parameter must be landed in every service's `service.yaml` first, or staggered behind a default.

## Common Pitfalls

- **Forgetting `id-token: write` on a new workflow.** OIDC silently fails with a confusing "could not assume role" — the fix is one line in `permissions:`.
- **Hardcoding role ARNs or account IDs in `service.yaml`.** Kills multi-environment reuse. The four required parameters exist precisely so the template stays account-agnostic.
- **Tagging images `:latest`.** Breaks traceability and rollback. Always `${{ github.sha }}`.
- **Writing a one-off deploy workflow instead of calling the reusable one.** Caching, build args, push retries, scan gates have to be added in N places later. Put it in `called-deploy-container-service.yaml` once.
- **Putting AWS creds in `secrets:` instead of using OIDC.** The pipeline is intentionally key-free — reintroducing static creds undoes the whole trust model.
- **Forgetting `kms:Decrypt` on the execution role when adding the first Secrets Manager secret.** `ssm:GetParameters` and `secretsmanager:GetSecretValue` alone aren't enough — Secrets Manager always KMS-encrypts at rest.
- **Pushing config values through GH Actions parameter overrides instead of into `service.yaml`.** Defeats the design — the whole reason for fetching from SSM/Secrets Manager at task start is keeping config out of CI.
- **`service.yaml` and `migration.yaml` `Secrets:` blocks drift.** Migrations and service code must read the same DB URL / config. Add new entries to both.
- **Putting a destructive change in expand instead of contract.** Old tasks are still running during the rollout. Drops/renames go in contract.
- **Changing the migration container `Name:` from `migrate`.** The composite action hardcodes it — the task will fail to start.
- **Bumping a package's code without bumping its `version`.** `check_versions` catches it on PR; if it slips through, CodeArtifact serves a stale wheel and the next service deploy ships old library code.
- **Pinning `poetry` to anything other than `1.8.3`.** `2.x` lockfile semantics differ; CI and Dockerfile both pin `1.8.3` for a reason.
- **Creating a new environment without setting all seven GH Actions variables.** The workflow fails mid-deploy rather than at a clean pre-check — read "Required GitHub Actions Variables" as a checklist.

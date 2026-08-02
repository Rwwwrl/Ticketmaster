---
name: deployment
description: Work safely with Ticketmaster deployment and AWS infrastructure. Use for test releases, GitHub Actions, ECR, CodeArtifact, CloudFormation, ECS Express Mode, Fargate migrations, Lambda, SSM, Secrets Manager, IAM, KMS, deployment diagnosis, or teardown.
---

# Ticketmaster Deployment

Use the repository workflows and templates as the source of truth. The only environment is `test-eu` in `eu-central-1`; never infer or invent production infrastructure.

## Locate Deployment Code

- `.github/workflows/on-push-test.yaml`: deployment trigger and orchestration
- `.github/workflows/called-deploy-container-service.yaml`: backend/frontend image and ECS deployment
- `.github/actions/run-ecs-migration/action.yaml`: one-shot migration task
- `.github/workflows/called-deploy-lambda.yaml`: Cognito PreSignUp Lambda deployment
- `.github/workflows/called-publish-python-package.yaml`: shared library publication
- `.github/workflows/on-pull-request.yaml`: validation gates
- `src/ticketmaster/{Dockerfile,service.yaml,migration.yaml}`: backend image and CloudFormation
- `frontend/{Dockerfile,service.yaml}`: frontend image and CloudFormation
- `src/lambdas/cognito_pre_signup/lambda.yaml`: Lambda infrastructure

## Preserve the Release Flow

A push to `test/**` triggers the test deployment. It uses GitHub OIDC, the `deploy-test-eu` concurrency group, and does not cancel an in-progress deployment.

The workflow:

1. Publish `src/libs` to CodeArtifact.
2. Build backend, frontend, and Lambda paths after library publication.
3. Build container images tagged with the Git SHA and push them to ECR.
4. For the backend, deploy `ticketmaster-test-eu-migrate`.
5. Run `poetry run alembic upgrade expand@head`.
6. Deploy `ticketmaster-test-eu`.
7. Run `poetry run alembic upgrade contract@head` only after a healthy service rollout.

Never reorder or collapse the expand → rollout → contract sequence. Stop after an expand failure. Do not run contract after a failed rollout.

The migration action discovers default-VPC networking, runs a public-IP Fargate task on cluster `default`, tails logs, and stops orphaned tasks on failure or timeout. Preserve command tokenization and orphan cleanup. Keep third-party actions pinned to immutable commit SHAs.

The backend image must contain `alembic.ini` and `migrations/` because the same image SHA serves the app and both migration phases.

## Keep Environment Configuration Complete

Use `eu-central-1` consistently in GitHub variables, resource ARNs, and `kms:ViaService` conditions.

Use these path conventions:

```text
/ticketmaster/<env>/<key>
/ticketmaster/<service>/<env>/<key>
```

Store non-secret configuration in SSM and sensitive values in Secrets Manager. Backend secrets currently include `POSTGRES_DB_URL`, `REDIS_URL`, `SECRET`, and `SENTRY_DSN`.

In ECS `ValueFrom`, use the Secrets Manager ARN without the generated `-XxXxXx` suffix. Match the runtime secret in IAM with an appropriate wildcard.

Whenever a required backend setting is added or renamed:

1. Update `src/ticketmaster/service.yaml`.
2. Update `src/ticketmaster/migration.yaml`; migrations import the full settings model.
3. Update test environment configuration.
4. Ensure the value exists in SSM or Secrets Manager for `test-eu`.

Preserve least-privilege roles. The backend task role is limited to required KMS public-key and Cognito delete actions; the Lambda role signs with its specific KMS key.

Expected GitHub environment variables include `AWS_REGION`, `AWS_ACCOUNT_ID`, `DEPLOYER_TO_AWS_ROLE_ARN`, `ECS_EXECUTION_ROLE_ARN`, `ECS_INFRASTRUCTURE_ROLE_ARN`, `CODEARTIFACT_DOMAIN`, and `CODEARTIFACT_REPOSITORY`.

## Prepare a Deployment Change

Before an explicitly requested deploy:

1. Inspect the branch and exact diff.
2. Confirm the target is `test-eu` in `eu-central-1`.
3. Bump package versions for changes under `src/libs/` or `src/ticketmaster/`. If the shared library version is unchanged, publication may skip it and the backend can install old code.
4. Verify settings are mirrored in service and migration templates.
5. Validate code, tests, and CloudFormation.
6. Report the exact branch, image/service scope, environment, and region.
7. Push or rerun a workflow only when the user's request authorizes that external mutation.

Do not expose secret values or CodeArtifact tokens in commands, logs, templates, or responses.

Run the PR-equivalent checks:

```bash
poetry run ruff check .
poetry run ruff format --check .
poetry run pytest --cov=src/libs/libs --cov=src/ticketmaster/ticketmaster --cov-report=term-missing --cov-fail-under=75
cfn-lint src/ticketmaster/service.yaml src/ticketmaster/migration.yaml frontend/service.yaml
```

Also lint `src/lambdas/cognito_pre_signup/lambda.yaml` when Lambda infrastructure changes.

## Diagnose Without Mutating

For explanation, status, review, or diagnosis requests, remain read-only. Inspect workflow runs, failed logs, stack events, ECS logs, and readiness without pushing, rerunning, deploying, or changing AWS resources.

Useful read-only commands include:

```bash
gh run list --workflow on-push-test.yaml --branch <test-branch>
gh run view <run-id> --log-failed
aws cloudformation describe-stack-events --stack-name ticketmaster-test-eu --region eu-central-1
aws logs tail /ecs/ticketmaster-test-eu --since 10m --region eu-central-1
```

Read the `ServiceUrl` CloudFormation output before probing `/readiness_check`.

The workflow may delete and recreate a service stack only when its initial creation left it exactly in `ROLLBACK_COMPLETE`. Do not broaden automatic deletion to other failure states.

## Treat Teardown as Destructive

`just aws-down env="test-eu" profile="tm-test"` deletes the backend, migration, frontend, and Lambda CloudFormation stacks. Run it only for an explicit teardown request after confirming the exact environment and profile. It does not remove external ECR, CodeArtifact, KMS, Cognito, database, Redis, SSM, or Secrets Manager prerequisites.

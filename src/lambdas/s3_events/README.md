# S3 Events Lambda

Triggered by S3 `ObjectCreated:*` events on the `ticketmaster-test-eu-media` bucket, filtered to the `event-trailer/` prefix. A **dumb forwarder**: it does one `HeadObject` (S3 event notifications carry no object metadata) and POSTs `{bucket, key, metadata}` to `POST /api/admin/s3-events` on the ticketmaster backend, signing a short-lived (60 s) PS256 JWT via `kms:Sign`. It interprets nothing about `metadata["kind"]` or `metadata["logical-identity"]` — all dispatch logic lives in the backend.

## Layout

```
s3_events/
    __init__.py
    handler.py      # entrypoint: lambda_handler(event, context)
pyproject.toml      # runtime deps (httpx, tenacity, boto3*) + dev deps (pytest, respx, pyjwt, cryptography)
tests/              # unit tests (boto3 KMS + S3 mocked, backend mocked via respx)
```

Lambda handler entrypoint: `s3_events.handler.lambda_handler`.

`*` boto3 is provided by the Lambda runtime; we still declare it for local dev.

## Required env vars

| Var                        | Source                                                                                                     |
| --------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `TICKETMASTER_API_URL`      | Set by `lambda.yaml` from SSM `/ticketmaster/ticketmaster/<env>/TICKETMASTER_API_URL`.                        |
| `AWS_REGION`                | Auto-injected by the Lambda runtime.                                                                          |
| `S3_EVENTS_JWT_KMS_KEY_ARN` | Set by `lambda.yaml` via SSM `/ticketmaster/ticketmaster/<env>/S3_EVENTS_JWT_KMS_KEY_ARN`.                     |
| `JWT_AUDIENCE`              | Set by `lambda.yaml` via SSM `/ticketmaster/ticketmaster/<env>/JWT_AUDIENCE`. Must match backend.              |
| `S3_EVENTS_JWT_ISSUER`      | Set by `lambda.yaml` via SSM `/ticketmaster/ticketmaster/<env>/S3_EVENTS_JWT_ISSUER`. Must match backend.      |
| `LAMBDA_ROLE_ARN`           | Set by `lambda.yaml` via `!GetAtt ExecutionRole.Arn`. Used as JWT `sub` for audit.                             |

Distinct `S3_EVENTS_*` names (not the cognito lambda's generic `JWT_KMS_KEY_ARN`/`JWT_ISSUER`) — the two lambdas' test suites share one root pytest `env` block, and reusing the generic names would force one issuer/key value across both.

## Provisioning model

Three layers, each owned by a different thing:

- **Manual, one-off per env** — not in this repo, done in the AWS Console:
  - Create the private S3 bucket (`ticketmaster-test-eu-media`, Block Public Access on).
  - Create the KMS asymmetric key (`RSA_2048`, key usage `SIGN_VERIFY`, region `eu-central-1`, alias `ticketmaster-test-eu-s3-events-jwt`). No key-policy edit needed beyond the default: the backend's Pod Identity role already holds `kms:GetPublicKey` account-wide via `AWSKeyManagementServicePowerUser`.
  - Write SSM params `/ticketmaster/ticketmaster/<env>/MEDIA_BUCKET`, `S3_EVENTS_JWT_KMS_KEY_ARN`, `S3_EVENTS_JWT_ISSUER`.
  - After the first CloudFormation deploy of this Lambda (below), wire the bucket's event notification (prefix `event-trailer/`, all object-create events) to invoke `ticketmaster-s3-events-<env>` — the S3 Console adds the required Lambda resource-based invoke permission automatically when the notification is saved.

- **Managed by `lambda.yaml` (CloudFormation)** — deployed from CI:
  - The Lambda function shell (`ticketmaster-s3-events-<env>`).
  - The Lambda execution IAM role + inline `kms:Sign` policy (on the S3 events KMS key) + inline `s3:GetObject` policy (on `<bucket>/event-trailer/*`, needed for `HeadObject`).
  - Env vars (resolved from SSM via `{{resolve:ssm:...}}`).

- **Managed by `aws-actions/aws-lambda-deploy`** — code only:
  - The Python zip uploaded on every push. The CFN template only declares a placeholder `ZipFile` for first-time create; subsequent CFN deploys see no Code diff and don't revert what `aws-lambda-deploy` uploaded.

## Build the deployment zip locally

```bash
cd src/lambdas/s3_events
rm -rf build && mkdir build
poetry export --without dev --without-hashes -f requirements.txt -o build/requirements.txt
pip install --target build/package -r build/requirements.txt
cp -r s3_events build/package/
cd build/package && zip -r ../lambda.zip . && cd ../..
# Result: build/lambda.zip — upload via Console or CI.
```

CI does the same via `.github/workflows/on-push-test.yaml` (which calls `called-deploy-lambda.yaml`).

## Run tests

```bash
cd src/lambdas/s3_events
poetry install
poetry run pytest
```

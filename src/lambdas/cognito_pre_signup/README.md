# Cognito PreSignUp Lambda

Synchronous blocking trigger fired by Cognito *before* it persists a new user. Calls `POST /v1/users/` on the ticketmaster backend, signing a short-lived (60 s) PS256 JWT via `kms:Sign`. Backend rejection → Cognito rejects sign-up → end user sees the error → no Cognito identity, no DB row.

## Layout

```
cognito_pre_signup/
    __init__.py
    handler.py      # entrypoint: lambda_handler(event, context)
pyproject.toml      # runtime deps (httpx, tenacity, boto3*) + dev deps (pytest, respx, pyjwt, cryptography)
tests/              # unit tests (boto3 KMS mocked, backend mocked via respx)
```

Lambda handler entrypoint: `cognito_pre_signup.handler.lambda_handler`.

`*` boto3 is provided by the Lambda runtime; we still declare it for local dev.

## Required env vars

| Var                    | Source                                                                                                 |
| ---------------------- | ------------------------------------------------------------------------------------------------------ |
| `TICKETMASTER_API_URL` | Set by `lambda.yaml` from the ticketmaster service stack's `ServiceUrl` output.                        |
| `AWS_REGION`           | Auto-injected by the Lambda runtime.                                                                   |
| `JWT_KMS_KEY_ARN`      | Set by `lambda.yaml` via SSM `/ticketmaster/ticketmaster/<env>/LAMBDA_JWT_KMS_KEY_ARN`.                |
| `JWT_AUDIENCE`         | Set by `lambda.yaml` via SSM `/ticketmaster/ticketmaster/<env>/JWT_AUDIENCE`. Must match backend.      |
| `JWT_ISSUER`           | Set by `lambda.yaml` via SSM `/ticketmaster/ticketmaster/<env>/LAMBDA_JWT_ISSUER`. Must match backend. |
| `LAMBDA_ROLE_ARN`      | Set by `lambda.yaml` via `!GetAtt ExecutionRole.Arn`. Used as JWT `sub` for audit.                     |

## Provisioning model

Three layers, each owned by a different thing:

- **Manual, one-off per env** — not in this repo, done in the AWS Console:
  - Create the KMS asymmetric key (`RSA_2048`, key usage `SIGN_VERIFY`, region `eu-central-1`); grant `kms:GetPublicKey` to the ticketmaster workload's IAM role (bound to its pod via EKS Pod Identity) via the key policy.
  - Write its ARN to SSM at `/ticketmaster/ticketmaster/<env>/LAMBDA_JWT_KMS_KEY_ARN`.
  - Write the SSM params `/ticketmaster/ticketmaster/<env>/JWT_AUDIENCE` and `LAMBDA_JWT_ISSUER`. These are shared with the `ticketmaster` service's ExternalSecret in `deploy/chart/`.
  - Wire this Lambda as the PreSignUp trigger on the Cognito User Pool.

- **Managed by `lambda.yaml` (CloudFormation)** — deployed from CI:
  - The Lambda function shell (`ticketmaster-cognito-pre-signup-<env>`).
  - The Lambda execution IAM role + inline `kms:Sign` policy on the KMS key.
  - Env vars (resolved from SSM via `{{resolve:ssm:...}}`).

- **Managed by `aws-actions/aws-lambda-deploy`** — code only:
  - The Python zip uploaded on every push. The CFN template only declares a placeholder `ZipFile` for first-time create; subsequent CFN deploys see no Code diff and don't revert what `aws-lambda-deploy` uploaded.

## Build the deployment zip locally

```bash
cd src/lambdas/cognito_pre_signup
rm -rf build && mkdir build
poetry export --without dev --without-hashes -f requirements.txt -o build/requirements.txt
pip install --target build/package -r build/requirements.txt
cp -r cognito_pre_signup build/package/
cd build/package && zip -r ../lambda.zip . && cd ../..
# Result: build/lambda.zip — upload via Console or CI.
```

CI does the same via `.github/workflows/on-push-test.yaml` (which calls `called-deploy-lambda.yaml`).

## Run tests

```bash
cd src/lambdas/cognito_pre_signup
poetry install
poetry run pytest
```

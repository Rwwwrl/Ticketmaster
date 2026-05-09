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

| Var | Source |
| --- | --- |
| `TICKETMASTER_API_URL` | Backend ALB URL (no trailing slash). |
| `AWS_REGION` | Auto-injected by the Lambda runtime. |
| `JWT_KMS_KEY_ARN` | ARN of the asymmetric KMS key Lambda signs with. |
| `JWT_AUDIENCE` | Must match backend `LAMBDA_JWT_AUDIENCE`. |
| `JWT_ISSUER` | Must match backend `LAMBDA_JWT_ISSUER`. |
| `LAMBDA_ROLE_ARN` | This Lambda's own execution role ARN. Used as JWT `sub` for audit. |

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

CI does the same via `.github/workflows/on-push-test-lambda.yaml`.

## Run tests

```bash
cd src/lambdas/cognito_pre_signup
poetry install
poetry run pytest
```

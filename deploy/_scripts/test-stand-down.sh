#!/usr/bin/env bash
set -euo pipefail

# NOTE @sosov: Full teardown of the test-eu EKS stand to stop node/control-plane/ALB
# billing between test sessions. Everything this script deletes is recreated by
# test-stand-up.sh; everything it leaves alone (IAM roles, KMS, Cognito, ECR,
# SSM/Secrets Manager, Postgres/Redis) is either free or holds data.

AWS_REGION="eu-central-1"
CLUSTER_NAME="ticketmaster-test-eu"
OIDC_PROVIDER_URL="oidc.eks.${AWS_REGION}.amazonaws.com"

export AWS_REGION

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "Not logged in. Run: aws sso login --profile tm-test-eu" >&2
  exit 1
fi

if ! aws eks describe-cluster --name "$CLUSTER_NAME" >/dev/null 2>&1; then
  echo "Cluster ${CLUSTER_NAME} does not exist — already down."
  exit 0
fi

echo "==> Updating kubeconfig for ${CLUSTER_NAME}"
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$AWS_REGION" >/dev/null

echo "==> Suspending Argo CD auto-sync (so selfHeal can't recreate the Ingress)"
kubectl -n argocd patch application application-test-eu --type merge \
  -p '{"spec":{"syncPolicy":{"automated":null}}}' 2>/dev/null \
  || echo "    Application application-test-eu not found — skipping"

echo "==> Deleting the Ingress and waiting for the ALB to be destroyed"
kubectl delete ingress ticketmaster --ignore-not-found --timeout=5m

echo "==> Deleting the cluster's IAM OIDC provider"
OIDC_ISSUER_ID="$(aws eks describe-cluster --name "$CLUSTER_NAME" \
  --query 'cluster.identity.oidc.issuer' --output text | sed 's#.*/id/##')"
OIDC_PROVIDER_ARN="arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):oidc-provider/${OIDC_PROVIDER_URL}/id/${OIDC_ISSUER_ID}"
aws iam delete-open-id-connect-provider --open-id-connect-provider-arn "$OIDC_PROVIDER_ARN" 2>/dev/null \
  || echo "    OIDC provider not found — skipping"

echo "==> Deleting cluster ${CLUSTER_NAME} (nodes/EBS/access-entries/pod-identity go with it)"
aws eks delete-cluster --name "$CLUSTER_NAME" >/dev/null
aws eks wait cluster-deleted --name "$CLUSTER_NAME"

cat <<EOF

Test stand is down.

Kept (not billed meaningfully, or holds data): IAM roles, KMS keys,
Secrets Manager secrets, SSM parameters, Cognito user pool, ECR images,
the Cognito pre-signup Lambda stack, your Postgres/Redis (external to
this account), the as-ticketmaster.com domain registration + hosted
zone, and the ACM certificate (auto-renews via its kept validation
CNAME). The test-eu.as-ticketmaster.com alias now points at a deleted
ALB until the next test-stand-up re-points it — harmless.

Run 'just test-stand-up' to rebuild.
EOF

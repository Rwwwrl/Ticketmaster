#!/usr/bin/env bash
set -euo pipefail

# NOTE @sosov: Rebuilds the test-eu EKS stand torn down by test-stand-down.sh.
# Idempotent — safe to re-run if it fails partway through. `env/test-eu` (git)
# stays the source of truth: once Argo CD is reinstalled and pointed at it, it
# restores the whole app with no CI run needed.

AWS_REGION="eu-central-1"
CLUSTER_NAME="ticketmaster-test-eu"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"

CLUSTER_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/ticketmaster-test-eu-eks-cluster"
NODE_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/ticketmaster-test-eu-eks-auto-node"
GITHUB_DEPLOYER_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/github-actions-deployer"
ESO_ROLE_NAME="ticketmaster-test-eu-eso"
TICKETMASTER_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/ticketmaster-test-eu-ticketmaster"
LAMBDA_FUNCTION_NAME="ticketmaster-cognito-pre-signup-test-eu"
API_URL_SSM_PARAM="/ticketmaster/ticketmaster/test-eu/TICKETMASTER_API_URL"

SUBNET_IDS="subnet-092acbfb9158e412b,subnet-09e535091c9ae236e,subnet-086a2225fe233ad7f"
KUBERNETES_VERSION="1.36"
# NOTE @sosov: Fixed AWS root-CA thumbprint used by every EKS-issued OIDC provider
# in this account/region — not specific to a cluster instance.
OIDC_ROOT_THUMBPRINT="06b25927c42a721631c1efd9431e648fa62e1e39"
METRICS_SERVER_ADDON_VERSION="v0.9.0-eksbuild.5"
ESO_CHART_VERSION="2.9.0"
ARGOCD_VERSION="v3.5.1"

export AWS_REGION

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "Not logged in. Run: aws sso login --profile tm-test-eu" >&2
  exit 1
fi

echo "==> Ensuring cluster ${CLUSTER_NAME} exists"
if aws eks describe-cluster --name "$CLUSTER_NAME" >/dev/null 2>&1; then
  echo "    Already exists — skipping create"
else
  aws eks create-cluster \
    --name "$CLUSTER_NAME" \
    --region "$AWS_REGION" \
    --kubernetes-version "$KUBERNETES_VERSION" \
    --role-arn "$CLUSTER_ROLE_ARN" \
    --resources-vpc-config "subnetIds=${SUBNET_IDS},endpointPublicAccess=true,endpointPrivateAccess=true" \
    --kubernetes-network-config "serviceIpv4Cidr=10.100.0.0/16,elasticLoadBalancing={enabled=true}" \
    --access-config "authenticationMode=API,bootstrapClusterCreatorAdminPermissions=true" \
    --compute-config "enabled=true,nodePools=general-purpose,system,nodeRoleArn=${NODE_ROLE_ARN}" \
    --storage-config "blockStorage={enabled=true}" >/dev/null
fi
aws eks wait cluster-active --name "$CLUSTER_NAME"

echo "==> Access entries"
aws eks create-access-entry --cluster-name "$CLUSTER_NAME" \
  --principal-arn "$GITHUB_DEPLOYER_ROLE_ARN" --type STANDARD >/dev/null 2>&1 \
  || echo "    github-actions-deployer entry already exists"
aws eks associate-access-policy --cluster-name "$CLUSTER_NAME" \
  --principal-arn "$GITHUB_DEPLOYER_ROLE_ARN" \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy \
  --access-scope type=cluster >/dev/null 2>&1 \
  || echo "    github-actions-deployer policy already associated"
aws eks create-access-entry --cluster-name "$CLUSTER_NAME" \
  --principal-arn "$NODE_ROLE_ARN" --type EC2 >/dev/null 2>&1 \
  || echo "    node role entry already exists"

echo "==> IRSA: rewiring ${ESO_ROLE_NAME} trust policy to the new cluster's OIDC issuer"
OIDC_ISSUER_URL="$(aws eks describe-cluster --name "$CLUSTER_NAME" \
  --query 'cluster.identity.oidc.issuer' --output text)"
OIDC_PROVIDER_HOST="${OIDC_ISSUER_URL#https://}"
OIDC_PROVIDER_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/${OIDC_PROVIDER_HOST}"

aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$OIDC_PROVIDER_ARN" >/dev/null 2>&1 \
  || aws iam create-open-id-connect-provider \
       --url "$OIDC_ISSUER_URL" \
       --client-id-list sts.amazonaws.com \
       --thumbprint-list "$OIDC_ROOT_THUMBPRINT" >/dev/null

cat >/tmp/eso-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Federated": "${OIDC_PROVIDER_ARN}"},
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "${OIDC_PROVIDER_HOST}:aud": "sts.amazonaws.com",
          "${OIDC_PROVIDER_HOST}:sub": "system:serviceaccount:default:eso"
        }
      }
    }
  ]
}
EOF
aws iam update-assume-role-policy --role-name "$ESO_ROLE_NAME" \
  --policy-document file:///tmp/eso-trust-policy.json
rm -f /tmp/eso-trust-policy.json

echo "==> Pod Identity association for the ticketmaster ServiceAccount"
aws eks create-pod-identity-association --cluster-name "$CLUSTER_NAME" \
  --namespace default --service-account ticketmaster \
  --role-arn "$TICKETMASTER_ROLE_ARN" >/dev/null 2>&1 \
  || echo "    Pod Identity association already exists"

echo "==> metrics-server addon"
aws eks create-addon --cluster-name "$CLUSTER_NAME" \
  --addon-name metrics-server --addon-version "$METRICS_SERVER_ADDON_VERSION" >/dev/null 2>&1 \
  || echo "    metrics-server addon already exists"

echo "==> Updating kubeconfig"
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$AWS_REGION" >/dev/null

echo "==> Installing External Secrets Operator ${ESO_CHART_VERSION}"
helm repo add external-secrets https://charts.external-secrets.io >/dev/null
helm repo update external-secrets >/dev/null
helm upgrade --install external-secrets external-secrets/external-secrets \
  --namespace external-secrets --create-namespace \
  --version "$ESO_CHART_VERSION" --wait

echo "==> Installing Argo CD ${ARGOCD_VERSION}"
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd -f "https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"
kubectl -n argocd rollout status deploy/argocd-server --timeout=5m
kubectl -n argocd rollout status statefulset/argocd-application-controller --timeout=5m

echo "==> Bootstrapping the Argo CD Application (this restores frontend + ticketmaster + Ingress)"
# NOTE @sosov: The Application manages itself from env/test-eu after this one apply;
# it is rendered from the chart so the spec has a single source of truth.
CHART_DIR="$(dirname "$0")/../chart"
helm template ticketmaster "$CHART_DIR" \
  -f "${CHART_DIR}/values.test.yaml" \
  --set commitSha=bootstrap \
  --show-only templates/argocd/application.yaml | kubectl apply -f -

echo "==> Waiting for the ALB hostname"
ALB_HOSTNAME=""
for _ in $(seq 1 60); do
  ALB_HOSTNAME="$(kubectl get ingress ticketmaster -n default \
    -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)"
  [ -n "$ALB_HOSTNAME" ] && break
  sleep 10
done
if [ -z "$ALB_HOSTNAME" ]; then
  echo "Timed out waiting for the ALB hostname — check 'kubectl -n argocd get application application-test-eu' and 'kubectl get ingress'." >&2
  exit 1
fi
echo "    ALB hostname: ${ALB_HOSTNAME}"

echo "==> Refreshing the ALB hostname in SSM and the Cognito pre-signup Lambda"
NEW_API_URL="http://${ALB_HOSTNAME}"
aws ssm put-parameter --name "$API_URL_SSM_PARAM" --value "$NEW_API_URL" --type String --overwrite >/dev/null

CURRENT_LAMBDA_ENV="$(aws lambda get-function-configuration --function-name "$LAMBDA_FUNCTION_NAME" \
  --query 'Environment.Variables' --output json)"
UPDATED_LAMBDA_ENV="$(echo "$CURRENT_LAMBDA_ENV" | jq --arg url "$NEW_API_URL" '.TICKETMASTER_API_URL = $url')"
aws lambda update-function-configuration --function-name "$LAMBDA_FUNCTION_NAME" \
  --environment "Variables=${UPDATED_LAMBDA_ENV}" >/dev/null

echo "==> Waiting for the app to become ready"
for _ in $(seq 1 30); do
  if curl -fs -o /dev/null "http://${ALB_HOSTNAME}/readiness-check"; then
    break
  fi
  sleep 10
done

ARGOCD_ADMIN_PASSWORD="$(kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || true)"

cat <<EOF

Test stand is up: http://${ALB_HOSTNAME}

Argo CD UI: 'just test-argocd-ui', then https://localhost:8080 (user 'admin').
$( [ -n "$ARGOCD_ADMIN_PASSWORD" ] && echo "Admin password (regenerated this cycle): ${ARGOCD_ADMIN_PASSWORD}" )
EOF

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
NODE_ROLE_NAME="ticketmaster-test-eu-eks-auto-node"
NODE_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${NODE_ROLE_NAME}"
GITHUB_DEPLOYER_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/github-actions-deployer"
ESO_ROLE_NAME="ticketmaster-test-eu-eso"
TICKETMASTER_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/ticketmaster-test-eu-ticketmaster"

APP_DOMAIN="test-eu.as-ticketmaster.com"
HOSTED_ZONE_ID="Z03658353OC69AMXF8YCD"

SUBNET_IDS="subnet-092acbfb9158e412b,subnet-09e535091c9ae236e,subnet-086a2225fe233ad7f"
KUBERNETES_VERSION="1.36"
NODE_INSTANCE_TYPE="t3a.medium"
NODES_PER_ZONE=1
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
    --compute-config '{"enabled":true,"nodePools":[]}' \
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
# NOTE @sosov: With the built-in node pools off, EKS no longer creates the node role's access
# entry or attaches its policy, so a custom NodeClass needs both done here.
aws eks create-access-entry --cluster-name "$CLUSTER_NAME" \
  --principal-arn "$NODE_ROLE_ARN" --type EC2 >/dev/null 2>&1 \
  || echo "    node role entry already exists"
aws eks associate-access-policy --cluster-name "$CLUSTER_NAME" \
  --principal-arn "$NODE_ROLE_ARN" \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSAutoNodePolicy \
  --access-scope type=cluster >/dev/null 2>&1 \
  || echo "    node role policy already associated"

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

echo "==> Static NodePools: ${NODES_PER_ZONE} ${NODE_INSTANCE_TYPE} node per subnet/AZ"
# NOTE @sosov: Auto Mode has no AWS API for custom node pools, so the NodeClass and NodePools are
# Kubernetes objects — but this script owns them and Argo CD never sees them. Change a pool by
# editing this script and re-running it (idempotent). Drift replacement is blocked below, so roll a
# node by hand: `kubectl delete nodeclaim <name>`. Expiry cannot be blocked: Auto Mode caps
# expireAfter + terminationGracePeriod (default 24h) at 21 days, hence 480h.
for CRD in nodepools.karpenter.sh nodeclasses.eks.amazonaws.com; do
  for _ in $(seq 1 30); do
    kubectl get crd "$CRD" >/dev/null 2>&1 && break
    sleep 10
  done
  kubectl get crd "$CRD" >/dev/null
done

SUBNET_LIST="${SUBNET_IDS//,/ }"
SUBNET_TERMS="$(echo "$SUBNET_IDS" | sed 's/[^,]*/{id: &}/g')"
CLUSTER_SG_ID="$(aws eks describe-cluster --name "$CLUSTER_NAME" \
  --query 'cluster.resourcesVpcConfig.clusterSecurityGroupId' --output text)"
kubectl apply -f - <<EOF
apiVersion: eks.amazonaws.com/v1
kind: NodeClass
metadata:
  name: static
spec:
  role: ${NODE_ROLE_NAME}
  subnetSelectorTerms: [${SUBNET_TERMS}]
  securityGroupSelectorTerms:
    - id: ${CLUSTER_SG_ID}
EOF

EXPECTED_NODES=0
for SUBNET_ID in $SUBNET_LIST; do
  AZ="$(aws ec2 describe-subnets --subnet-ids "$SUBNET_ID" \
    --query 'Subnets[0].AvailabilityZone' --output text)"
  kubectl apply -f - <<EOF
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: static-${AZ}
spec:
  replicas: ${NODES_PER_ZONE}
  limits:
    nodes: $((NODES_PER_ZONE + 1))
  disruption:
    consolidateAfter: Never
    budgets:
      - nodes: "0"
        reasons: [Drifted]
  template:
    spec:
      nodeClassRef:
        group: eks.amazonaws.com
        kind: NodeClass
        name: static
      expireAfter: 480h
      requirements:
        - {key: topology.kubernetes.io/zone, operator: In, values: [${AZ}]}
        - {key: node.kubernetes.io/instance-type, operator: In, values: [${NODE_INSTANCE_TYPE}]}
        - {key: karpenter.sh/capacity-type, operator: In, values: [on-demand]}
EOF
  EXPECTED_NODES=$((EXPECTED_NODES + NODES_PER_ZONE))
done

echo "==> Waiting for ${EXPECTED_NODES} Ready nodes"
READY_NODES=0
for _ in $(seq 1 60); do
  READY_NODES="$(kubectl get nodes --no-headers 2>/dev/null | awk '$2=="Ready"' | wc -l | tr -d ' ' || true)"
  [ "$READY_NODES" -ge "$EXPECTED_NODES" ] && break
  sleep 10
done
if [ "$READY_NODES" -lt "$EXPECTED_NODES" ]; then
  echo "Timed out: ${READY_NODES}/${EXPECTED_NODES} nodes Ready — check 'kubectl get nodepools,nodeclaims' and 'kubectl describe nodeclass static'." >&2
  exit 1
fi

echo "==> Installing External Secrets Operator ${ESO_CHART_VERSION}"
helm repo add external-secrets https://charts.external-secrets.io >/dev/null
helm repo update external-secrets >/dev/null
helm upgrade --install external-secrets external-secrets/external-secrets \
  --namespace external-secrets --create-namespace \
  --version "$ESO_CHART_VERSION" --wait

echo "==> Installing Argo CD ${ARGOCD_VERSION}"
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
# NOTE @sosov: --server-side is required — the applicationsets.argoproj.io CRD is too
# large for client-side apply's last-applied-configuration annotation (256KiB cap).
kubectl apply -n argocd --server-side --force-conflicts \
  -f "https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"
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

echo "==> Upserting Route53 alias ${APP_DOMAIN} -> ${ALB_HOSTNAME}"
ALB_CANONICAL_ZONE_ID="$(aws elbv2 describe-load-balancers \
  --query "LoadBalancers[?DNSName=='${ALB_HOSTNAME}'].CanonicalHostedZoneId" --output text)"
if [ -z "$ALB_CANONICAL_ZONE_ID" ] || [ "$ALB_CANONICAL_ZONE_ID" = "None" ]; then
  echo "Could not resolve the ALB's canonical hosted zone id for ${ALB_HOSTNAME}" >&2
  exit 1
fi
CHANGE_ID="$(aws route53 change-resource-record-sets --hosted-zone-id "$HOSTED_ZONE_ID" \
  --change-batch "$(jq -n --arg name "$APP_DOMAIN" --arg dns "$ALB_HOSTNAME" --arg zone "$ALB_CANONICAL_ZONE_ID" \
    '{Changes:[{Action:"UPSERT",ResourceRecordSet:{Name:$name,Type:"A",AliasTarget:{HostedZoneId:$zone,DNSName:$dns,EvaluateTargetHealth:false}}}]}')" \
  --query 'ChangeInfo.Id' --output text)"
aws route53 wait resource-record-sets-changed --id "$CHANGE_ID"

echo "==> Waiting for the app to become ready"
for _ in $(seq 1 30); do
  if curl -fs -o /dev/null "https://${APP_DOMAIN}/readiness-check"; then
    break
  fi
  sleep 10
done

ARGOCD_ADMIN_PASSWORD="$(kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || true)"

cat <<EOF

Test stand is up: https://${APP_DOMAIN} (ALB hostname: ${ALB_HOSTNAME})

Argo CD UI: 'just test-argocd-ui', then https://localhost:8080 (user 'admin').
$( [ -n "$ARGOCD_ADMIN_PASSWORD" ] && echo "Admin password (regenerated this cycle): ${ARGOCD_ADMIN_PASSWORD}" )
EOF

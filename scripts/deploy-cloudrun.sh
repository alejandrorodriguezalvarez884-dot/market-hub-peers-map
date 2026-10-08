#!/usr/bin/env bash
# Deploys the production image (site + API in one container) to Google Cloud Run. Cloud Build
# builds the Dockerfile remotely, so Docker is not needed locally. A Cloud Storage bucket keeps
# the prices read from Yahoo. The service scales to zero: it costs nothing while nobody uses it,
# and it calls no paid API.
#
# Requirements: the gcloud CLI logged in on a project with billing enabled, and .env with HUB_URL.
# HUB_URL (the Market Hub address) admits only people signed in there: the service reads the
# hub's session cookie with the hub's secret (Secret Manager: market-hub-session-secret).
#
# Optional overrides: GCP_PROJECT, GCP_REGION, SERVICE_NAME, MAX_INSTANCES.
set -euo pipefail

cd "$(dirname "$0")/.."

fail() {
  echo "error: $*" >&2
  exit 1
}

command -v gcloud >/dev/null || fail "gcloud is not installed."

GCP_PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
GCP_REGION="${GCP_REGION:-europe-west1}"
SERVICE_NAME="${SERVICE_NAME:-peer-map}"
MAX_INSTANCES="${MAX_INSTANCES:-2}"
ENV_FILE=".env"

[[ -n "$GCP_PROJECT" ]] || fail "No GCP project selected. Run 'gcloud init' or set GCP_PROJECT."
[[ -f "$ENV_FILE" ]] || fail "$ENV_FILE not found."
[[ -f src/peermap/peers.json ]] || fail "src/peermap/peers.json is missing: build the map first (make peers)."
BUCKET="${PEERMAP_BUCKET:-${GCP_PROJECT}-peer-map}"

# Read single values instead of sourcing the file, and drop the quotes around them.
env_value() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' || true; }
HUB_URL="$(env_value HUB_URL)"

gcp() { gcloud --project "$GCP_PROJECT" --quiet "$@"; }

# Give the service's account a role on something, only if it does not have it yet. A policy is
# one document: two deploys writing it at the same moment collide ("concurrent policy changes"),
# and the second fails. Reading it first means that in the ordinary deploy nothing is written,
# so the services' deploys can run side by side.
grant() {
  local kind="$1" resource="$2" role="$3" member="serviceAccount:$SERVICE_ACCOUNT"
  shift 3
  # $kind is left unquoted on purpose: "storage buckets" is two words of the command. grep reads
  # the whole answer (no -q): leaving early would break the pipe, and that would read as "missing".
  if gcp $kind get-iam-policy "$resource" --flatten='bindings[].members' --format='value(bindings.role,bindings.members)' 2>/dev/null \
      | tr -d '\r' | grep -xF "$role"$'\t'"$member" >/dev/null; then
    return 0
  fi
  gcp $kind add-iam-policy-binding "$resource" --member "$member" --role "$role" "$@" >/dev/null
}

echo "→ Enabling APIs in $GCP_PROJECT"
gcp services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com storage.googleapis.com

# Source deploys build with, and run as, the Compute Engine default service account.
PROJECT_NUMBER="$(gcp projects describe "$GCP_PROJECT" --format='value(projectNumber)')"
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
grant projects "$GCP_PROJECT" roles/run.builder --condition=None

SECRETS=()
HUB_ENV=""
if [[ -n "$HUB_URL" ]]; then
  gcp secrets describe market-hub-session-secret >/dev/null 2>&1 || fail "HUB_URL is set but Market Hub's secret market-hub-session-secret does not exist. Deploy the hub first."
  grant secrets market-hub-session-secret roles/secretmanager.secretAccessor
  SECRETS=(--set-secrets "HUB_SESSION_SECRET=market-hub-session-secret:latest")
  HUB_ENV="|HUB_URL=$HUB_URL"
  echo "→ Behind Market Hub's sign-in ($HUB_URL)"
else
  echo "note: HUB_URL is not set: the service will be open to anyone."
fi

echo "→ Bucket gs://$BUCKET"
if ! gcp storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then
  gcp storage buckets create "gs://$BUCKET" --location "$GCP_REGION" --uniform-bucket-level-access \
    --public-access-prevention >/dev/null
fi
grant "storage buckets" "gs://$BUCKET" roles/storage.objectAdmin

echo "→ Building with Cloud Build and deploying '$SERVICE_NAME' to $GCP_REGION (a few minutes)"
# The timeout leaves room for a refresh of the prices: some 1,500 companies asked from Yahoo.
gcp run deploy "$SERVICE_NAME" \
  --source . \
  --region "$GCP_REGION" \
  --allow-unauthenticated \
  --port 8080 \
  --cpu 1 \
  --memory 1Gi \
  --min-instances 0 \
  --max-instances "$MAX_INSTANCES" \
  --timeout 300 \
  ${SECRETS[@]+"${SECRETS[@]}"} \
  --set-env-vars "^|^PEERMAP_BUCKET=$BUCKET$HUB_ENV"

URL="$(gcp run services describe "$SERVICE_NAME" --region "$GCP_REGION" --format 'value(status.url)')"
if curl -fsS "$URL/api/health" >/dev/null 2>&1; then
  echo "✓ Deployed: $URL"
else
  fail "Deployed, but $URL/api/health failed. Logs: gcloud run services logs read $SERVICE_NAME --region $GCP_REGION"
fi

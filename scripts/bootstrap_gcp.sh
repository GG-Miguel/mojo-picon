#!/usr/bin/env bash
# One-time GCP setup for deploying Mojo Picón from GitLab CI (Infraestructura y CI-CD).
# Idempotent: every step checks or tolerates "already exists", so it can be run again safely.
#
# Least privilege (Module 4):
#   - Cloud Run runs as mojo-run: Firestore, Vertex AI, Firebase Auth read, and only the
#     Langfuse and Qdrant secrets.
#   - GitLab CI deploys as gitlab-deploy through Workload Identity Federation (no keys), only
#     from protected branches of GG-Miguel/mojo-picon. It can deploy new revisions (run.developer)
#     but not change who can call the service; it writes only to this project's image repository
#     and to its own Cloud Build bucket.
#   - The evaluation gate in GitLab CI runs as gitlab-eval, through the same federation and only
#     from protected branches: it may call Vertex AI and read the Qdrant secret, nothing else.
#   - Public access (allUsers may call the service; the app checks Firebase tokens) is granted
#     once here, by the project owner, on a placeholder service that the first CI deploy replaces.
#
# Usage: bash scripts/bootstrap_gcp.sh            (prints each command before running it)
set -euo pipefail

PROJECT="${GCP_PROJECT_ID:-mojo-picon}"
REGION="${GCP_REGION:-europe-west1}"
REPO="mojo-picon"
SERVICE="mojo-picon"
BUILD_BUCKET="$PROJECT-cloudbuild-src"
RUN_SA="mojo-run"
DEPLOY_SA="gitlab-deploy"
EVAL_SA="gitlab-eval"
POOL="gitlab"
PROVIDER="gitlab-com"
GITLAB_PROJECT="GG-Miguel/mojo-picon"
SECRETS=(langfuse-public-key langfuse-secret-key qdrant-api-key)
PLACEHOLDER_IMAGE="us-docker.pkg.dev/cloudrun/container/hello" # Google's sample image

run() { echo "+ $*"; "$@"; }
# IAM is eventually consistent: a service account created seconds ago may not be visible yet
retry() {
  local attempt
  for attempt in 1 2 3 4 5 6; do
    "$@" && return 0
    echo "  (not visible yet, retrying in 10 s: $attempt/6)"
    sleep 10
  done
  return 1
}
exists() { "$@" >/dev/null 2>&1; }

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
RUN_SA_EMAIL="$RUN_SA@$PROJECT.iam.gserviceaccount.com"
DEPLOY_SA_EMAIL="$DEPLOY_SA@$PROJECT.iam.gserviceaccount.com"
EVAL_SA_EMAIL="$EVAL_SA@$PROJECT.iam.gserviceaccount.com"

# --- APIs -----------------------------------------------------------------------------
run gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  aiplatform.googleapis.com firestore.googleapis.com secretmanager.googleapis.com \
  iamcredentials.googleapis.com sts.googleapis.com --project "$PROJECT"

# --- Image repository, with a cleanup policy ----------------------------------------------
exists gcloud artifacts repositories describe "$REPO" --location "$REGION" --project "$PROJECT" ||
  run gcloud artifacts repositories create "$REPO" --repository-format docker --location "$REGION" \
    --description "Mojo Picón images" --project "$PROJECT"
# Keep release images (tags v…) and the 10 most recent; delete the rest (not the running image:
# it is always among the most recent).
POLICY_FILE="$(mktemp)"
cat >"$POLICY_FILE" <<'JSON'
[
  {"name": "keep-releases", "action": {"type": "Keep"}, "condition": {"tagState": "TAGGED", "tagPrefixes": ["v"]}},
  {"name": "keep-recent", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 10}},
  {"name": "delete-rest", "action": {"type": "Delete"}, "condition": {"tagState": "ANY"}}
]
JSON
run gcloud artifacts repositories set-cleanup-policies "$REPO" --location "$REGION" --project "$PROJECT" \
  --policy "$POLICY_FILE" --quiet >/dev/null  # without --dry-run: the policy is active
rm -f "$POLICY_FILE"

# --- Cloud Build source bucket (regional, only for this project's builds) -----------------
exists gcloud storage buckets describe "gs://$BUILD_BUCKET" --project "$PROJECT" ||
  run gcloud storage buckets create "gs://$BUILD_BUCKET" --location "$REGION" --uniform-bucket-level-access \
    --project "$PROJECT"

# --- Cloud Run runtime identity -------------------------------------------------------
exists gcloud iam service-accounts describe "$RUN_SA_EMAIL" --project "$PROJECT" ||
  run gcloud iam service-accounts create "$RUN_SA" --display-name "Mojo Picón (Cloud Run)" --project "$PROJECT"
for role in roles/datastore.user roles/aiplatform.user roles/firebaseauth.viewer; do
  retry run gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$RUN_SA_EMAIL" \
    --role "$role" --condition None --quiet >/dev/null
done

# --- Secrets (Langfuse, Qdrant): created empty; the owner adds the values in the console -------------
for secret in "${SECRETS[@]}"; do
  exists gcloud secrets describe "$secret" --project "$PROJECT" ||
    run gcloud secrets create "$secret" --replication-policy user-managed --locations "$REGION" --project "$PROJECT"
  retry run gcloud secrets add-iam-policy-binding "$secret" --project "$PROJECT" \
    --member "serviceAccount:$RUN_SA_EMAIL" --role roles/secretmanager.secretAccessor --quiet >/dev/null
done

# --- GitLab deploy identity ------------------------------------------------------------
exists gcloud iam service-accounts describe "$DEPLOY_SA_EMAIL" --project "$PROJECT" ||
  run gcloud iam service-accounts create "$DEPLOY_SA" --display-name "GitLab CI deploys" --project "$PROJECT"
# Project-level: deploy revisions, submit builds, write build logs, use the project's APIs
for role in roles/run.developer roles/cloudbuild.builds.editor roles/logging.logWriter \
  roles/serviceusage.serviceUsageConsumer; do
  retry run gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$DEPLOY_SA_EMAIL" \
    --role "$role" --condition None --quiet >/dev/null
done
# Resource-level: only this image repository and this build bucket
retry run gcloud artifacts repositories add-iam-policy-binding "$REPO" --location "$REGION" --project "$PROJECT" \
  --member "serviceAccount:$DEPLOY_SA_EMAIL" --role roles/artifactregistry.writer --quiet >/dev/null
retry run gcloud storage buckets add-iam-policy-binding "gs://$BUILD_BUCKET" \
  --member "serviceAccount:$DEPLOY_SA_EMAIL" --role roles/storage.admin --quiet >/dev/null
# It may run the service as mojo-run, and run Cloud Build as itself
for sa in "$RUN_SA_EMAIL" "$DEPLOY_SA_EMAIL"; do
  retry run gcloud iam service-accounts add-iam-policy-binding "$sa" --project "$PROJECT" \
    --member "serviceAccount:$DEPLOY_SA_EMAIL" --role roles/iam.serviceAccountUser --quiet >/dev/null
done

# --- Workload Identity Federation for GitLab (protected branches of this project only) ------
exists gcloud iam workload-identity-pools describe "$POOL" --location global --project "$PROJECT" ||
  run gcloud iam workload-identity-pools create "$POOL" --location global --display-name "GitLab" --project "$PROJECT"
exists gcloud iam workload-identity-pools providers describe "$PROVIDER" --workload-identity-pool "$POOL" \
  --location global --project "$PROJECT" ||
  run gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" --workload-identity-pool "$POOL" \
    --location global --project "$PROJECT" --issuer-uri "https://gitlab.com" \
    --allowed-audiences "https://gitlab.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.project_path=assertion.project_path,attribute.ref=assertion.ref,attribute.ref_protected=assertion.ref_protected" \
    --attribute-condition "assertion.project_path == '$GITLAB_PROJECT' && assertion.ref_protected == 'true'"
retry run gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA_EMAIL" --project "$PROJECT" \
  --role roles/iam.workloadIdentityUser --quiet >/dev/null \
  --member "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.project_path/$GITLAB_PROJECT"

# --- GitLab evaluation identity (CI gate): Vertex AI and the Qdrant secret only ----------------
exists gcloud iam service-accounts describe "$EVAL_SA_EMAIL" --project "$PROJECT" ||
  run gcloud iam service-accounts create "$EVAL_SA" --display-name "GitLab CI evaluation gate" --project "$PROJECT"
for role in roles/aiplatform.user roles/serviceusage.serviceUsageConsumer; do
  retry run gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$EVAL_SA_EMAIL" \
    --role "$role" --condition None --quiet >/dev/null
done
retry run gcloud secrets add-iam-policy-binding qdrant-api-key --project "$PROJECT" \
  --member "serviceAccount:$EVAL_SA_EMAIL" --role roles/secretmanager.secretAccessor --quiet >/dev/null
retry run gcloud iam service-accounts add-iam-policy-binding "$EVAL_SA_EMAIL" --project "$PROJECT" \
  --role roles/iam.workloadIdentityUser --quiet >/dev/null \
  --member "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.project_path/$GITLAB_PROJECT"

# --- Cloud Run service: placeholder + public access, once ---------------------------------
exists gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" ||
  run gcloud run deploy "$SERVICE" --image "$PLACEHOLDER_IMAGE" --region "$REGION" --project "$PROJECT" \
    --service-account "$RUN_SA_EMAIL" --max-instances 1 --no-allow-unauthenticated --quiet
run gcloud run services add-iam-policy-binding "$SERVICE" --region "$REGION" --project "$PROJECT" \
  --member allUsers --role roles/run.invoker --quiet >/dev/null

cat <<OUT

Done. In GitLab (Settings → CI/CD → Variables; not secrets, can be visible):
  GCP_PROJECT_ID    = $PROJECT
  GCP_REGION        = $REGION
  GCP_WIF_PROVIDER  = projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/providers/$PROVIDER
  GCP_DEPLOY_SA     = $DEPLOY_SA_EMAIL
  GCP_EVAL_SA       = $EVAL_SA_EMAIL      (evaluation gate; without it the gate job is skipped)
  GCP_BUILD_BUCKET  = $BUILD_BUCKET

Before the first deploy, add the Langfuse keys as secret versions (Google Cloud console →
Security → Secret Manager → ${SECRETS[*]} → New version). Cloud Run cannot start without them.
Service URL: $(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format 'value(status.url)')
OUT

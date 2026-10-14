#!/usr/bin/env bash
# One-time GCP setup for deploying Mojo Picón from GitLab CI (Infraestructura y CI-CD).
# Idempotent: every step checks or tolerates "already exists", so it can be run again safely.
#
# Creates:
#   - APIs: Cloud Run, Artifact Registry, Cloud Build, Vertex AI, Firestore, IAM credentials, STS
#   - Artifact Registry repository for the images (europe-west1)
#   - Service account for Cloud Run (least privilege: Firestore, Vertex AI, Firebase Auth read)
#   - Service account for GitLab deploys + Workload Identity Federation (no keys), restricted to
#     protected branches of GitLab project GG-Miguel/mojo-picon
#
# Usage: bash scripts/bootstrap_gcp.sh            (prints each command before running it)
set -euo pipefail

PROJECT="${GCP_PROJECT_ID:-mojo-picon}"
REGION="${GCP_REGION:-europe-west1}"
REPO="mojo-picon"
RUN_SA="mojo-run"
DEPLOY_SA="gitlab-deploy"
POOL="gitlab"
PROVIDER="gitlab-com"
GITLAB_PROJECT="GG-Miguel/mojo-picon"

run() { echo "+ $*"; "$@"; }
exists() { "$@" >/dev/null 2>&1; }

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
RUN_SA_EMAIL="$RUN_SA@$PROJECT.iam.gserviceaccount.com"
DEPLOY_SA_EMAIL="$DEPLOY_SA@$PROJECT.iam.gserviceaccount.com"

run gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  aiplatform.googleapis.com firestore.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  --project "$PROJECT"

exists gcloud artifacts repositories describe "$REPO" --location "$REGION" --project "$PROJECT" ||
  run gcloud artifacts repositories create "$REPO" --repository-format docker --location "$REGION" \
    --description "Mojo Picón images" --project "$PROJECT"

# --- Cloud Run runtime identity -------------------------------------------------------
exists gcloud iam service-accounts describe "$RUN_SA_EMAIL" --project "$PROJECT" ||
  run gcloud iam service-accounts create "$RUN_SA" --display-name "Mojo Picón (Cloud Run)" --project "$PROJECT"
for role in roles/datastore.user roles/aiplatform.user roles/firebaseauth.viewer; do
  run gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$RUN_SA_EMAIL" \
    --role "$role" --condition None --quiet >/dev/null
done

# --- GitLab deploy identity (Workload Identity Federation) -----------------------------
exists gcloud iam service-accounts describe "$DEPLOY_SA_EMAIL" --project "$PROJECT" ||
  run gcloud iam service-accounts create "$DEPLOY_SA" --display-name "GitLab CI deploys" --project "$PROJECT"
for role in roles/run.admin roles/artifactregistry.writer roles/cloudbuild.builds.editor roles/storage.admin \
  roles/serviceusage.serviceUsageConsumer roles/logging.logWriter; do
  run gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$DEPLOY_SA_EMAIL" \
    --role "$role" --condition None --quiet >/dev/null
done
# The deployer may run the service as the runtime identity, and run Cloud Build as itself
for sa in "$RUN_SA_EMAIL" "$DEPLOY_SA_EMAIL"; do
  run gcloud iam service-accounts add-iam-policy-binding "$sa" --project "$PROJECT" \
    --member "serviceAccount:$DEPLOY_SA_EMAIL" --role roles/iam.serviceAccountUser --quiet >/dev/null
done

exists gcloud iam workload-identity-pools describe "$POOL" --location global --project "$PROJECT" ||
  run gcloud iam workload-identity-pools create "$POOL" --location global --display-name "GitLab" --project "$PROJECT"
exists gcloud iam workload-identity-pools providers describe "$PROVIDER" --workload-identity-pool "$POOL" \
  --location global --project "$PROJECT" ||
  run gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" --workload-identity-pool "$POOL" \
    --location global --project "$PROJECT" --issuer-uri "https://gitlab.com" \
    --allowed-audiences "https://gitlab.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.project_path=assertion.project_path,attribute.ref=assertion.ref,attribute.ref_protected=assertion.ref_protected" \
    --attribute-condition "assertion.project_path == '$GITLAB_PROJECT' && assertion.ref_protected == 'true'"
run gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA_EMAIL" --project "$PROJECT" \
  --role roles/iam.workloadIdentityUser --quiet >/dev/null \
  --member "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.project_path/$GITLAB_PROJECT"

cat <<OUT

Done. Add these CI/CD variables in GitLab (Settings → CI/CD → Variables; not secrets, can be visible):
  GCP_PROJECT_ID          = $PROJECT
  GCP_REGION              = $REGION
  GCP_WIF_PROVIDER        = projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/providers/$PROVIDER
  GCP_DEPLOY_SA           = $DEPLOY_SA_EMAIL
OUT

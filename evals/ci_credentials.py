"""Credentials for the evaluation gate in GitLab CI, without keys and without gcloud in the image.

    python -m evals.ci_credentials adc     -> writes .ci_gcp_creds.json (Workload Identity Federation)
    python -m evals.ci_credentials qdrant  -> prints the Qdrant key from Secret Manager (for an export)

GitLab's OIDC token (in .ci_oidc_token) is exchanged for short-lived credentials of the gitlab-eval
service account, which can only call Vertex AI and read the qdrant-api-key secret
(scripts/bootstrap_gcp.sh). Only protected branches get the token (the provider's condition).
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

CREDS = Path(".ci_gcp_creds.json")
TOKEN_FILE = Path(".ci_oidc_token")
SECRET = "qdrant-api-key"


def write_adc() -> None:
    """External account configuration, the same file `gcloud iam workload-identity-pools create-cred-config` writes."""
    provider, account = os.environ["GCP_WIF_PROVIDER"], os.environ["GCP_EVAL_SA"]
    config = {
        "type": "external_account",
        "audience": f"//iam.googleapis.com/{provider}",
        "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
        "token_url": "https://sts.googleapis.com/v1/token",
        "credential_source": {"file": str(TOKEN_FILE.resolve())},
        "service_account_impersonation_url": (
            f"https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{account}:generateAccessToken"
        ),
    }
    CREDS.write_text(json.dumps(config), encoding="utf-8")


def qdrant_key() -> str:
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    project = os.environ.get("GCP_PROJECT_ID", "mojo-picon")
    url = f"https://secretmanager.googleapis.com/v1/projects/{project}/secrets/{SECRET}/versions/latest:access"
    response = AuthorizedSession(credentials).get(url, timeout=30)
    response.raise_for_status()
    return base64.b64decode(response.json()["payload"]["data"]).decode()


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "adc":
        write_adc()
    elif command == "qdrant":
        print(qdrant_key(), end="")
    else:
        sys.exit("usage: python -m evals.ci_credentials adc|qdrant")

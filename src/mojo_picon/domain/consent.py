"""The user's acceptance of the terms and the privacy policy, before any data is processed.

Mojo Picón gives general guidance, is not a health professional and has no medical purpose; still, a user
may write data that the GDPR could treat as health data (allergies, a condition), so the acceptance is an
explicit consent (art. 9.2.a) and the API serves nothing until it exists (Privacidad y RGPD).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

# Bump it when the text of the terms or the privacy policy changes: users accept the new version again.
CONSENT_VERSION = "2026-10-23"


class Consent(BaseModel):
    version: str
    accepted_at: datetime

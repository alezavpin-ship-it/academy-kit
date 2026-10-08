"""Who is using the academy when it runs on Azure App Service behind Microsoft Entra ID (App Service Authentication,
"Easy Auth").

App Service signs the person in before the request reaches the app and adds their identity to every request:

    X-MS-CLIENT-PRINCIPAL-NAME   the sign-in name (user principal name / e-mail)
    X-MS-CLIENT-PRINCIPAL        base64 JSON with the token claims (display name, e-mail…)

The headers are trusted ONLY when the app is told it runs behind that sign-in (ACADEMY_AUTH=entra, set in the Web App's
settings): App Service strips these headers from what the browser sends, so nobody can fake them there. On a laptop
(ACADEMY_AUTH unset) they are ignored and the sidebar keeps the «Who are you?» list.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass

NAME_HEADER = "X-MS-CLIENT-PRINCIPAL-NAME"
PRINCIPAL_HEADER = "X-MS-CLIENT-PRINCIPAL"
NAME_CLAIMS = ("name", "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name")
MAIL_CLAIMS = ("preferred_username", "email", "upn", "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
               "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn")


@dataclass(frozen=True)
class SignedIn:
    email: str
    name: str


def enabled(env: dict | None = None) -> bool:
    return (env if env is not None else os.environ).get("ACADEMY_AUTH", "").strip().lower() == "entra"


def _get(headers, key: str) -> str:
    if not headers:
        return ""
    for k in (key, key.lower(), key.title()):
        v = headers.get(k) if hasattr(headers, "get") else None
        if v:
            return str(v).strip()
    lowered = {str(k).lower(): v for k, v in dict(headers).items()}
    return str(lowered.get(key.lower(), "") or "").strip()


def _claims(raw: str) -> dict[str, str]:
    try:
        data = json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return {c.get("typ", ""): c.get("val", "") for c in data.get("claims", []) if isinstance(c, dict)}


def signed_in(headers, env: dict | None = None) -> SignedIn | None:
    """The person App Service signed in, or None (not on Azure, or sign-in not configured)."""
    if not enabled(env):
        return None
    email = _get(headers, NAME_HEADER)
    claims = _claims(_get(headers, PRINCIPAL_HEADER))
    email = email or next((claims[c] for c in MAIL_CLAIMS if claims.get(c)), "")
    if not email:
        return None
    name = next((claims[c] for c in NAME_CLAIMS if claims.get(c) and claims[c] != email), "")
    return SignedIn(email=email, name=name or email.split("@")[0].replace(".", " ").title())

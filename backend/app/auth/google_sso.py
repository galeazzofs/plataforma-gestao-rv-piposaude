import requests
from flask import current_app

# Outbound calls to Google must never hang a worker indefinitely.
_TIMEOUT_SECONDS = 10


class GoogleSSOError(Exception):
    pass


def exchange_code_for_tokens(code):
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": current_app.config["GOOGLE_CLIENT_ID"],
            "client_secret": current_app.config["GOOGLE_CLIENT_SECRET"],
            "redirect_uri": current_app.config["GOOGLE_REDIRECT_URI"],
            "grant_type": "authorization_code",
        },
        timeout=_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        raise GoogleSSOError(f"Token exchange failed: {response.text}")
    return response.json()


def get_user_info(access_token):
    response = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        raise GoogleSSOError(f"User info fetch failed: {response.text}")
    info = response.json()
    # Accounts are auto-created from this email — an unverified address must
    # never mint a session.
    if info.get("verified_email") is not True:
        raise GoogleSSOError("Google account email is not verified")
    return info


def validate_email_domain(email):
    domain = email.split("@")[-1].strip().lower()
    allowed = [d.lower() for d in current_app.config["ALLOWED_EMAIL_DOMAINS"]]
    if domain not in allowed:
        raise GoogleSSOError(
            f"Email domain {domain} not allowed. Must be one of: "
            + ", ".join(f"@{d}" for d in allowed)
        )
    return True

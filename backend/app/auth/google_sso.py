import requests
from flask import current_app


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
    )
    if response.status_code != 200:
        raise GoogleSSOError(f"Token exchange failed: {response.text}")
    return response.json()


def get_user_info(access_token):
    response = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code != 200:
        raise GoogleSSOError(f"User info fetch failed: {response.text}")
    return response.json()


def validate_email_domain(email):
    domain = email.split("@")[-1]
    allowed = current_app.config["ALLOWED_EMAIL_DOMAIN"]
    if domain != allowed:
        raise GoogleSSOError(f"Email domain {domain} not allowed. Must be @{allowed}")
    return True

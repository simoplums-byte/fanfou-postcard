#!/usr/bin/env python3
"""Compare Fanfou protected API access with requests-oauthlib."""

import subprocess

import requests
from requests_oauthlib import OAuth1


def secret(service: str) -> str:
    return subprocess.check_output(
        [
            "security",
            "find-generic-password",
            "-a",
            "fanfou-postcard",
            "-s",
            service,
            "-w",
        ],
        text=True,
    ).strip()


auth = OAuth1(
    secret("fanfou-postcard.consumer-key"),
    client_secret=secret("fanfou-postcard.consumer-secret"),
    resource_owner_key=secret("fanfou-postcard.access-token"),
    resource_owner_secret=secret("fanfou-postcard.access-token-secret"),
    signature_method="HMAC-SHA1",
    signature_type="AUTH_HEADER",
)

session = requests.Session()
for name, path, params in (
    ("verify_credentials", "/account/verify_credentials.json", None),
    ("timeline", "/statuses/user_timeline.json", {"count": "1", "mode": "lite"}),
):
    request = requests.Request(
        "GET", "http://api.fanfou.com" + path, params=params, auth=auth
    ).prepare()
    request.url = request.url.replace("http://", "https://", 1)
    response = session.send(request, timeout=(5, 15))
    print(f"{name}_http={response.status_code}")
    if response.ok:
        payload = response.json()
        if name == "verify_credentials":
            print(f"account_id={payload.get('id', '')}")
            print(f"reported_statuses_count={payload.get('statuses_count', '')}")
        else:
            print(f"timeline_records={len(payload) if isinstance(payload, list) else 0}")
    else:
        print(f"{name}_error={response.text[:512]}")


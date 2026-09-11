#!/usr/bin/env python3
"""Minimal Fanfou OAuth 1.0 probe using credentials in macOS Keychain."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import getpass
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


KEYCHAIN_ACCOUNT = "fanfou-postcard"
KEYCHAIN_KEY_SERVICE = "fanfou-postcard.consumer-key"
KEYCHAIN_SECRET_SERVICE = "fanfou-postcard.consumer-secret"
REQUEST_TOKEN_URL = "https://fanfou.com/oauth/request_token"
REQUEST_TOKEN_SIGNATURE_URL = "http://fanfou.com/oauth/request_token"
AUTHORIZE_URL = "https://fanfou.com/oauth/authorize"
AUTHORIZE_URL_FILE = "/tmp/fanfou-postcard-authorize-url"
ACCESS_TOKEN_URL = "https://fanfou.com/oauth/access_token"
ACCESS_TOKEN_SIGNATURE_URL = "http://fanfou.com/oauth/access_token"
API_URL = "https://api.fanfou.com"
API_SIGNATURE_URL = "http://api.fanfou.com"


def keychain_password(service: str) -> str:
    result = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-a",
            KEYCHAIN_ACCOUNT,
            "-s",
            service,
            "-w",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.rstrip("\n")


def percent(value: str) -> str:
    return urllib.parse.quote(value, safe="~-._")


def oauth_header(
    method: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    *,
    token: str | None = None,
    token_secret: str = "",
    verifier: str | None = None,
    request_params: dict[str, str] | None = None,
    callback: bool = False,
    realm: bool = False,
) -> str:
    params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_version": "1.0",
    }
    if callback:
        params["oauth_callback"] = "oob"
    if token:
        params["oauth_token"] = token
    if verifier:
        params["oauth_verifier"] = verifier
    signature_params = {**(request_params or {}), **params}
    normalized = "&".join(
        f"{percent(key)}={percent(value)}"
        for key, value in sorted(signature_params.items())
    )
    base_string = "&".join((method.upper(), percent(url), percent(normalized)))
    signing_key = f"{percent(consumer_secret)}&{percent(token_secret)}"
    digest = hmac.new(
        signing_key.encode(), base_string.encode(), hashlib.sha1
    ).digest()
    params["oauth_signature"] = base64.b64encode(digest).decode()
    prefix = 'OAuth realm="", ' if realm else "OAuth "
    return prefix + ", ".join(
        f'{percent(key)}="{percent(value)}"' for key, value in sorted(params.items())
    )


def request_token(timeout: float) -> int:
    consumer_key = keychain_password(KEYCHAIN_KEY_SERVICE)
    consumer_secret = keychain_password(KEYCHAIN_SECRET_SERVICE)
    request = urllib.request.Request(
        REQUEST_TOKEN_URL,
        headers={
            "Authorization": oauth_header(
                "GET", REQUEST_TOKEN_SIGNATURE_URL, consumer_key, consumer_secret
                , callback=True
            ),
            "User-Agent": "Fanfou-Postcard/0.1 OAuth-Probe",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        print(f"request-token failed: HTTP {error.code}", file=sys.stderr)
        detail = error.read(512).decode("utf-8", "replace").strip()
        if detail:
            print(f"server response: {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as error:
        print(f"request-token failed: {error.reason}", file=sys.stderr)
        return 1

    values = urllib.parse.parse_qs(body, strict_parsing=True)
    token = values.get("oauth_token", [None])[0]
    token_secret = values.get("oauth_token_secret", [None])[0]
    if not token or not token_secret:
        print("request-token failed: response omitted token fields", file=sys.stderr)
        return 1

    subprocess.run(
        [
            "security",
            "add-generic-password",
            "-a",
            KEYCHAIN_ACCOUNT,
            "-s",
            "fanfou-postcard.request-token",
            "-w",
            token,
            "-U",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "security",
            "add-generic-password",
            "-a",
            KEYCHAIN_ACCOUNT,
            "-s",
            "fanfou-postcard.request-token-secret",
            "-w",
            token_secret,
            "-U",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    authorize_url = (
        f"{AUTHORIZE_URL}?oauth_token={percent(token)}&oauth_callback=oob"
    )
    fd = os.open(
        AUTHORIZE_URL_FILE,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write(authorize_url)
    print(f"request-token succeeded; authorize URL saved to {AUTHORIZE_URL_FILE}")
    return 0


def save_keychain(service: str, value: str) -> None:
    subprocess.run(
        [
            "security",
            "add-generic-password",
            "-a",
            KEYCHAIN_ACCOUNT,
            "-s",
            service,
            "-w",
            value,
            "-U",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def exchange_token(timeout: float) -> int:
    consumer_key = keychain_password(KEYCHAIN_KEY_SERVICE)
    consumer_secret = keychain_password(KEYCHAIN_SECRET_SERVICE)
    request_token_value = keychain_password("fanfou-postcard.request-token")
    request_token_secret = keychain_password("fanfou-postcard.request-token-secret")
    verifier = getpass.getpass("OAuth PIN: ").strip()
    if not verifier:
        print("access-token failed: PIN is empty", file=sys.stderr)
        return 1
    request = urllib.request.Request(
        ACCESS_TOKEN_URL,
        headers={
            "Authorization": oauth_header(
                "GET",
                ACCESS_TOKEN_SIGNATURE_URL,
                consumer_key,
                consumer_secret,
                token=request_token_value,
                token_secret=request_token_secret,
                verifier=verifier,
            ),
            "User-Agent": "Fanfou-Postcard/0.1 OAuth-Probe",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        print(f"access-token failed: HTTP {error.code}", file=sys.stderr)
        detail = error.read(512).decode("utf-8", "replace").strip()
        if detail:
            print(f"server response: {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as error:
        print(f"access-token failed: {error.reason}", file=sys.stderr)
        return 1

    values = urllib.parse.parse_qs(body, strict_parsing=True)
    access_token = values.get("oauth_token", [None])[0]
    access_secret = values.get("oauth_token_secret", [None])[0]
    if not access_token or not access_secret:
        print("access-token failed: response omitted token fields", file=sys.stderr)
        return 1
    save_keychain("fanfou-postcard.access-token", access_token)
    save_keychain("fanfou-postcard.access-token-secret", access_secret)
    print("access-token succeeded and was saved to macOS Keychain")
    return 0


def api_get(path: str, query: dict[str, str], timeout: float):
    consumer_key = keychain_password(KEYCHAIN_KEY_SERVICE)
    consumer_secret = keychain_password(KEYCHAIN_SECRET_SERVICE)
    access_token = keychain_password("fanfou-postcard.access-token")
    access_secret = keychain_password("fanfou-postcard.access-token-secret")
    request_url = API_URL + path + ".json"
    signature_url = API_SIGNATURE_URL + path + ".json"
    if query:
        request_url += "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(
        request_url,
        headers={
            "Authorization": oauth_header(
                "GET",
                signature_url,
                consumer_key,
                consumer_secret,
                token=access_token,
                token_secret=access_secret,
                request_params=query,
                realm=True,
            ),
            "User-Agent": "Fanfou-Postcard/0.1 OAuth-Probe",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def verify_api(timeout: float) -> int:
    failures = 0
    checks = (
        ("verify_credentials", "/account/verify_credentials", {}),
        ("timeline", "/statuses/user_timeline", {"count": "1", "mode": "lite"}),
    )
    for name, path, query in checks:
        try:
            status, payload = api_get(path, query, timeout)
            print(f"{name}_http={status}")
            if name == "verify_credentials":
                print(f"account_id={payload.get('id', '')}")
                print(f"account_name={payload.get('name') or payload.get('screen_name', '')}")
                print(f"reported_statuses_count={payload.get('statuses_count', '')}")
            else:
                print(f"timeline_records={len(payload) if isinstance(payload, list) else 0}")
        except urllib.error.HTTPError as error:
            failures += 1
            detail = error.read(512).decode("utf-8", "replace").strip()
            print(f"{name}_http={error.code}")
            print(f"{name}_error={detail}")
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            failures += 1
            print(f"{name}_error={error}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--exchange", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.exchange:
        return exchange_token(args.timeout)
    if args.verify:
        return verify_api(args.timeout)
    return request_token(args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())

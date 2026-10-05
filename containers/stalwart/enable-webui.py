#!/usr/bin/env python3
"""Enable this image's bundled Web UI on an already configured Stalwart server."""
import argparse
import base64
import getpass
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

BUNDLE_URL = "file:///usr/share/stalwart/webui.zip"
UPSTREAM_URL = "https://github.com/stalwartlabs/webui/releases/latest/download/webui.zip"


def envelope(method, arguments):
    return {"using": ["urn:ietf:params:jmap:core", "urn:stalwart:jmap"],
            "methodCalls": [[method, arguments, "bundle"]]}


def result(response, method):
    responses = response.get("methodResponses", [])
    if len(responses) != 1 or responses[0][0] != method or responses[0][2] != "bundle":
        raise ValueError(f"{method} was rejected; check administrator permissions and complete initial setup first")
    data = responses[0][1]
    if any(data.get(key) for key in ("notCreated", "notUpdated", "notDestroyed")):
        raise ValueError(f"{method} reported an object error; no successful update is assumed")
    return data


def enable(call):
    """Only change the existing built-in UI; preserve other Application settings."""
    apps = call("x:Application/get", {"properties": ["id", "urlPrefix", "resourceUrl"]})["list"]
    matches = [app for app in apps
               if {"/admin", "/account"}.issubset({"/" + p.strip("/") for p in app["urlPrefix"]})
               and app["resourceUrl"] in (UPSTREAM_URL, BUNDLE_URL)]
    if len(matches) != 1:
        raise ValueError("Expected one built-in Web UI Application; refusing to change custom or ambiguous applications")
    app_id = matches[0]["id"]
    updated = call("x:Application/set", {"update": {app_id: {"resourceUrl": BUNDLE_URL, "enabled": True}}})
    if app_id not in updated.get("updated", {}):
        raise ValueError("Stalwart did not confirm the Application update")
    current = call("x:Application/get", {"ids": [app_id], "properties": ["id", "resourceUrl", "enabled"]})
    if len(current["list"]) != 1 or current["list"][0]["resourceUrl"] != BUNDLE_URL or not current["list"][0]["enabled"]:
        raise ValueError("Application settings failed readback")
    refreshed = call("x:Action/set", {"create": {"refresh": {"@type": "UpdateApps"}}})
    if "refresh" not in refreshed.get("created", {}):
        raise ValueError("Stalwart did not confirm the application refresh")
    return app_id


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def base_url(value):
    url = urllib.parse.urlsplit(value)
    if url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
        raise ValueError("Use the server origin, without credentials, path, query or fragment")
    if not url.hostname or (url.scheme != "https" and not (
            url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1"))):
        raise ValueError("Use HTTPS, or HTTP on localhost through a trusted local connection")
    return value.rstrip("/")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Stalwart origin, for example https://mail.example.org")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password-file", type=Path, help="Optional private password file; otherwise prompt securely")
    args = parser.parse_args()
    origin = base_url(args.url)
    password = args.password_file.read_text().rstrip("\r\n") if args.password_file else getpass.getpass("Stalwart password: ")
    if not password or ":" in args.user:
        raise ValueError("Invalid username or empty password")
    authorization = "Basic " + base64.b64encode(f"{args.user}:{password}".encode()).decode()
    opener = urllib.request.build_opener(NoRedirect())

    def request(path, body=None):
        headers = {"Content-Type": "application/json"}
        # Credentials are sent only to the management endpoint on the chosen origin.
        if body is not None:
            headers["Authorization"] = authorization
        req = urllib.request.Request(origin + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers)
        try:
            with opener.open(req, timeout=90) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            raise ValueError(f"Stalwart returned HTTP {error.code}; credentials and response bodies were not printed") from None

    def call(method, arguments):
        return result(json.loads(request("/jmap", envelope(method, arguments))), method)

    app_id = enable(call)
    html = request("/admin/index.html").decode()
    scripts = re.findall(r'<script[^>]+src="\./(assets/[^"<>]+\.js)"', html)
    if not scripts or not request("/admin/" + scripts[0]):
        raise ValueError("Application updated, but the UI/JavaScript readiness check failed")
    print(f"Enabled bundled Web UI for Application {app_id}: {origin}/admin/")
    print("Run this command again after an image upgrade to refresh Stalwart's cached bundle.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, urllib.error.URLError) as error:
        raise SystemExit(str(error)) from None

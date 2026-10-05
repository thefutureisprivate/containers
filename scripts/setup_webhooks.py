#!/usr/bin/env python3
"""Prepare package-scoped OBS refresh hooks; optionally install them in GitHub."""
import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import obs

REPOSITORY = "thefutureisprivate/containers"


def prepare(output):
    credential_file = os.environ.get("OBS_CREDENTIALS_FILE")
    if not credential_file:
        raise ValueError("Set OBS_CREDENTIALS_FILE to an external credential file")
    client = obs.Client(credential_file)
    user, _ = obs.credentials(credential_file)
    tokens = ET.fromstring(client.request("GET", f"/person/{user}/token"))
    hooks = []
    for name in ["obs-service-container_policy", *obs.package_manifest()]:
        description = "Containers Git refresh: " + name
        existing = next((e for e in tokens if e.get("description") == description
                         and e.get("project") == obs.project() and e.get("package") == name
                         and e.get("enabled") == "true"), None)
        if existing is not None:
            token_id, secret = existing.get("id"), existing.get("string")
        else:
            # Always bind to a real package. Never create account-wide tokens.
            result = ET.fromstring(client.request("POST", f"/person/{user}/token", b"", {
                "operation": "runservice", "project": obs.project(), "package": name,
                "description": description,
            }))
            token_id = result.findtext("data[@name='id']")
            secret = result.findtext("data[@name='token']")
        if not token_id or not secret:
            raise ValueError(f"{name}: OBS did not return the scoped refresh token")
        hooks.append({"package": name, "name": "web", "active": True, "events": ["push"],
                      "config": {"url": f"https://api.opensuse.org/trigger/webhook?id={token_id}",
                                 "content_type": "json", "secret": secret, "insecure_ssl": "0"}})
    output = Path(output).resolve()
    if output.is_relative_to(obs.ROOT):
        raise ValueError("Store webhook secrets outside the Git repository")
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(hooks, stream, indent=2)
    print(f"Prepared {len(hooks)} package-scoped hooks in {output}; secrets were not printed")


def install(configuration, token_file):
    token = Path(token_file).read_text().strip()
    opener = urllib.request.build_opener(obs.NoRedirect())

    def request(method, suffix, body=None):
        url = f"https://api.github.com/repos/{REPOSITORY}/hooks" + suffix
        req = urllib.request.Request(url, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                     "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"})
        try:
            with opener.open(req, timeout=30) as response:
                content = response.read()
                return json.loads(content) if content else None
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"GitHub webhook {method}: HTTP {error.code}") from None

    existing = request("GET", "?per_page=100")
    for hook in json.loads(Path(configuration).read_text()):
        package = hook.pop("package")
        found = next((e for e in existing if e["config"]["url"] == hook["config"]["url"]), None)
        if found:
            result = request("PATCH", "/" + str(found["id"]), hook)
        else:
            result = request("POST", "", hook)
        check = request("GET", "/" + str(result["id"]))
        if not check["active"] or check["events"] != ["push"] or check["config"]["url"] != hook["config"]["url"]:
            raise ValueError(f"{package}: webhook settings failed readback")
        print(f"Installed GitHub push hook for {package} (hook {result['id']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    preparation = sub.add_parser("prepare")
    preparation.add_argument("output", help="New private file outside the repository")
    installation = sub.add_parser("install")
    installation.add_argument("configuration")
    installation.add_argument("--github-token-file", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.output)
    else:
        install(args.configuration, args.github_token_file)

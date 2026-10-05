#!/usr/bin/env python3
"""Configure OBS Git builds and verify its OpenPGP container signatures."""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.opensuse.org"
REGISTRY = "registry.opensuse.org"
REPOSITORY = "containers"
KEY = ROOT / "keys/obs-project.asc"
FINGERPRINT = ROOT / "keys/obs-project.fingerprint"


def project():
    return ET.parse(ROOT / "obs/project.xml").getroot().attrib["name"]


def credentials(path):
    """Read credentials without sourcing shell code or printing secret values."""
    text = Path(path).read_text()
    if text.lstrip().startswith("{"):
        data = json.loads(text)
        user, password = data["username"], data["password"]
    else:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) not in (2, 3):
            raise ValueError("Use JSON username/password, or username and password on separate lines (optional leading label).")
        user, password = lines[-2:]
    if not isinstance(user, str) or not isinstance(password, str) or not user or not password or ":" in user:
        raise ValueError("Invalid OBS credentials format")
    return user, password


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the OBS Authorization header to another location.
        return None


class Client:
    def __init__(self, credential_file=None):
        self.authorization = None
        if credential_file:
            user, password = credentials(credential_file)
            self.authorization = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, path, data=None, query=None, missing_ok=False):
        if method != "GET" and not self.authorization:
            raise ValueError("Set OBS_CREDENTIALS_FILE to a credential file outside the repository.")
        prefix = "" if self.authorization else "/public"
        url = API + prefix + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {"Content-Type": "application/octet-stream"}
        if self.authorization:
            headers["Authorization"] = self.authorization
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=300) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            # Error bodies may echo request data. Never print them or headers.
            raise RuntimeError(f"OBS {method} {path}: HTTP {exc.code}") from None


def source_path(package=None, filename=None):
    parts = ["source", project()]
    if package:
        parts.append(package)
    if filename:
        parts.append(filename)
    return "/" + "/".join(urllib.parse.quote(p, safe=":") for p in parts)


def package_manifest():
    return json.loads((ROOT / "containers/obs-service-container_policy/images.json").read_text())


def check():
    sys.path.insert(0, str(ROOT / "containers/obs-service-container_policy"))
    from policy import check_recipe
    for name in package_manifest():
        check_recipe(ROOT / "containers" / name, name)
        service = ET.parse(ROOT / "containers" / name / "_service").getroot()
        if service.find("service[@name='container_policy'][@mode='buildtime']") is None:
            raise ValueError(f"{name}: missing OBS build-time policy service")
        print(f"Validated OBS recipe: {name}")
    ET.parse(ROOT / "obs/project.xml")
    if list((ROOT / ".github/workflows").glob("*")):
        raise ValueError("GitHub workflows are outside this OBS-only build architecture")


def fingerprint(key_bytes):
    with tempfile.TemporaryDirectory(prefix="obs-gpg-") as tmp:
        output = subprocess.run(
            ["gpg", "--homedir", tmp, "--batch", "--with-colons", "--import-options", "show-only", "--import"],
            input=key_bytes, capture_output=True, check=True,
        ).stdout.decode()
    keys = [line for line in output.splitlines() if line.startswith("pub:")]
    fingerprints = [line.split(":")[9] for line in output.splitlines() if line.startswith("fpr:")]
    if len(keys) != 1 or not fingerprints:
        raise ValueError("Expected exactly one OBS project public key")
    fields = keys[0].split(":")
    if fields[1] in {"i", "r", "e", "d"}:
        created = datetime.fromtimestamp(int(fields[5]), timezone.utc).isoformat()
        raise ValueError(f"OBS public key is not currently valid (created {created}). If it is in the future, wait for clock skew to clear before publishing; do not disable verification.")
    return fingerprints[0]


def pin_key(client):
    data = client.request("GET", source_path(filename="_pubkey"))
    actual = fingerprint(data)
    if FINGERPRINT.exists() and FINGERPRINT.read_text().strip() != actual:
        raise ValueError("OBS signing key changed; review the rotation before updating the pinned key.")
    KEY.parent.mkdir(exist_ok=True)
    KEY.write_bytes(data)
    FINGERPRINT.write_text(actual + "\n")
    print(f"Pinned OBS project public key: {actual}")


def configure(client):
    """Apply topology and bind each real OBS package to its Git directory."""
    check()
    desired = (ROOT / "obs/project.xml").read_bytes()
    client.request("PUT", source_path(filename="_meta"), desired)
    if client.request("GET", source_path(filename="_pubkey"), missing_ok=True) is None:
        client.request("POST", source_path(), b"", {"cmd": "createkey"})
    pin_key(client)
    client.request("PUT", source_path(filename="_config"), (ROOT / "_config").read_bytes())
    for name in ["obs-service-container_policy", *package_manifest()]:
        meta = ET.Element("package", name=name, project=project())
        ET.SubElement(meta, "title").text = name
        ET.SubElement(meta, "description").text = "Built, checked, signed and published by OBS from Git."
        ET.SubElement(meta, "scmsync").text = (
            "https://github.com/thefutureisprivate/containers?subdir=containers/" + name + "#main")
        client.request("PUT", source_path(name, "_meta"), ET.tostring(meta))
    print(f"Configured OBS Git builds: {project()}")


def refresh(client):
    for name in ["obs-service-container_policy", *package_manifest()]:
        client.request("POST", source_path(name), b"", {"cmd": "runservice"})
    print("Requested OBS to fetch the current main branch")


def image_reference(package, tag="latest"):
    if package not in package_manifest() or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag):
        raise ValueError("Unknown package or invalid image tag")
    namespace = project().lower().replace(":", "/")
    return f"{REGISTRY}/{namespace}/{REPOSITORY}/{package}:{tag}"


def policy(key_path):
    scope = f"{REGISTRY}/{project().lower().replace(':', '/')}/{REPOSITORY}"
    return {
        "default": [{"type": "reject"}],
        "transports": {"docker": {scope: [{
            "type": "signedBy", "keyType": "GPGKeys", "keyPath": str(key_path.resolve()),
            "signedIdentity": {"type": "matchRepoDigestOrExact"},
        }]}},
    }


def trusted_key():
    if not KEY.exists() or not FINGERPRINT.exists():
        raise ValueError("Missing pinned project public key; bootstrap the OBS project first.")
    if fingerprint(KEY.read_bytes()) != FINGERPRINT.read_text().strip():
        raise ValueError("Public key does not match the pinned fingerprint")


def verify(package, tag, destination=None):
    image = image_reference(package, tag)
    trusted_key()
    target = Path(destination).resolve() if destination else None
    if target:
        if target.exists():
            raise ValueError("Verification destination must not exist; choose an empty output path.")
        target.parent.mkdir(parents=True, exist_ok=True)
    # Stage locally and expose a retained destination only after verification.
    with tempfile.TemporaryDirectory(prefix="obs-verify-", dir=target.parent if target else None) as tmp:
        tmp = Path(tmp)
        (tmp / "policy.json").write_text(json.dumps(policy(KEY)))
        registry_dir = tmp / "registries.d"
        registry_dir.mkdir()
        (registry_dir / "obs.yaml").write_text(
            f"docker:\n  {REGISTRY}:\n    lookaside: https://{REGISTRY}/sigstore\n"
        )
        output = tmp / "image"
        # inspect alone does not enforce a signature policy; copy does.
        subprocess.run([
            "skopeo", "--policy", str(tmp / "policy.json"), "--registries.d", str(registry_dir),
            "--override-os", "linux", "--override-arch", "amd64", "copy", "--preserve-digests",
            f"docker://{image}", f"dir:{output}",
        ], check=True)
        manifest = (output / "manifest.json").read_bytes()
        print(f"Verified {image}")
        print("Manifest digest: sha256:" + hashlib.sha256(manifest).hexdigest())
        if target:
            output.rename(target)
            print(f"Verified image and signatures saved in {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "configure", "refresh", "status"):
        sub.add_parser(command)
    log = sub.add_parser("log")
    log.add_argument("package", choices=list(package_manifest()))
    verification = sub.add_parser("verify")
    verification.add_argument("package", choices=list(package_manifest()))
    verification.add_argument("--tag", default="latest")
    verification.add_argument("--destination", help="Keep the verified image in a new directory")
    args = parser.parse_args()
    if args.command == "check":
        check()
    elif args.command == "verify":
        verify(args.package, args.tag, args.destination)
    else:
        client = Client(os.environ.get("OBS_CREDENTIALS_FILE"))
        if args.command == "configure":
            configure(client)
        elif args.command == "refresh":
            refresh(client)
        elif args.command == "status":
            print(client.request("GET", f"/build/{project()}/_result").decode())
        elif args.command == "log":
            print(client.request("GET", f"/build/{project()}/{REPOSITORY}/x86_64/{args.package}/_log", query={"nostream": "1"}).decode())


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError, ET.ParseError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

#!/usr/bin/env python3
"""Build/publish through OBS; verify its GPG simple-signing signatures locally."""

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
            with self.opener.open(req, timeout=45) as response:
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


def packages():
    manifest = json.loads((ROOT / "obs/packages.json").read_text())
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError("obs/packages.json must list at least one package")
    result = {}
    for package, filenames in manifest.items():
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", package):
            raise ValueError("Invalid package name")
        if not isinstance(filenames, list) or "Dockerfile" not in filenames or len(filenames) != len(set(filenames)):
            raise ValueError(f"{package}: list unique source files, including Dockerfile")
        directory = ROOT / "containers" / package
        if directory.is_symlink():
            raise ValueError(f"{package}: symlinked source directories are not supported")
        sources = {}
        for name in filenames:
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
                raise ValueError(f"{package}: source names must be simple filenames")
            path = directory / name
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"{package}/{name}: expected a regular source file")
            sources[name] = path.read_bytes()
        result[package] = sources
    return result


def filelist(sources):
    root = ET.Element("directory")
    for name, data in sorted(sources.items()):
        # MD5 is OBS's source transport identifier, not the trust mechanism.
        ET.SubElement(root, "entry", name=name,
                      md5=hashlib.md5(data, usedforsecurity=False).hexdigest(),
                      hash="sha256:" + hashlib.sha256(data).hexdigest())
    return ET.tostring(root)


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


def bootstrap(client):
    desired = (ROOT / "obs/project.xml").read_bytes()
    current = client.request("GET", source_path(filename="_meta"), missing_ok=True)
    if current is None:
        client.request("PUT", source_path(filename="_meta"), desired)
        print(f"Created {project()}")
    else:
        def normalized(data):
            root = ET.fromstring(data)
            for element in root.iter():
                element.text = (element.text or "").strip() or None
                element.tail = None
            return ET.tostring(root)
        if normalized(current) != normalized(desired):
            raise ValueError("Existing OBS project metadata differs; reconcile obs/project.xml with OBS before bootstrapping.")
        print(f"Project already configured: {project()}")
    config = (ROOT / "obs/project.conf").read_bytes()
    current = client.request("GET", source_path(filename="_config"), missing_ok=True)
    if current and current.strip() != config.strip():
        raise ValueError("Existing OBS project configuration differs; refusing to overwrite it.")
    if not current:
        client.request("PUT", source_path(filename="_config"), config)
    # Only create a key when this project has none; never rotate an existing key.
    if client.request("GET", source_path(filename="_pubkey"), missing_ok=True) is None:
        client.request("POST", source_path(), b"", {"cmd": "createkey"})
    pin_key(client)


def publish(client):
    # Validate the entire allowlist before making any remote changes.
    for package, sources in packages().items():
        path = source_path(package)
        meta = client.request("GET", path + "/_meta", missing_ok=True)
        if meta is None:
            root = ET.Element("package", name=package, project=project())
            ET.SubElement(root, "title").text = f"{package} container"
            ET.SubElement(root, "description").text = "Built from the containers repository; signed and published by OBS."
            client.request("PUT", path + "/_meta", ET.tostring(root))
        elif ET.fromstring(meta).find("scmsync") is not None:
            raise ValueError(f"{package} is managed by SCM sync; refusing to overwrite its sources")
        current = ET.fromstring(client.request("GET", path))
        remote_files = {entry.attrib["name"]: entry.attrib["md5"] for entry in current.findall("entry")}
        wanted = filelist(sources)
        wanted_files = {entry.attrib["name"]: entry.attrib["md5"] for entry in ET.fromstring(wanted)}
        extra = remote_files.keys() - sources.keys()
        if extra:
            raise ValueError(f"{package}: unexpected remote files {sorted(extra)}; inspect them before removing anything")
        if remote_files == wanted_files:
            check_source_bytes(client, package, current, sources)
            print(f"{package}: sources already current")
            continue
        # Stage blobs first. One commitfilelist publishes the complete revision.
        for name, data in sorted(sources.items()):
            if remote_files.get(name) != wanted_files[name]:
                client.request("PUT", source_path(package, name), data, {"rev": "repository"})
        latest = ET.fromstring(client.request("GET", path))
        if latest.attrib.get("srcmd5") != current.attrib.get("srcmd5"):
            raise ValueError(f"{package}: OBS sources changed during upload; retry after reviewing the change")
        response = ET.fromstring(client.request("POST", path, wanted, {
            "cmd": "commitfilelist", "comment": "Publish reviewed container sources from the local repository",
        }))
        if response.tag != "directory" or response.get("error"):
            raise RuntimeError(f"{package}: OBS did not accept the complete source revision")
        # Read back the committed file hashes rather than assuming upload succeeded.
        committed = ET.fromstring(client.request("GET", path))
        actual = {entry.attrib["name"]: entry.attrib["md5"] for entry in committed.findall("entry")}
        if actual != wanted_files:
            raise RuntimeError(f"{package}: committed OBS sources differ from local sources")
        check_source_bytes(client, package, committed, sources)
        print(f"{package}: committed OBS revision {committed.get('rev')}")


def check_source_bytes(client, package, revision, sources):
    rev = revision.get("srcmd5") or revision.get("rev")
    if not rev:
        raise RuntimeError(f"{package}: OBS did not identify the committed source revision")
    for name, expected in sorted(sources.items()):
        actual = client.request("GET", source_path(package, name), query={"rev": rev})
        if hashlib.sha256(actual).digest() != hashlib.sha256(expected).digest():
            raise RuntimeError(f"{package}/{name}: SHA-256 readback mismatch")


def image_reference(package, tag="latest"):
    if package not in packages() or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag):
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
    for command in ("check", "bootstrap", "publish", "status"):
        sub.add_parser(command)
    log = sub.add_parser("log")
    log.add_argument("package", choices=list(packages()))
    verification = sub.add_parser("verify")
    verification.add_argument("package", choices=list(packages()))
    verification.add_argument("--tag", default="latest")
    verification.add_argument("--destination", help="Keep the verified image in a new directory")
    args = parser.parse_args()
    if args.command == "check":
        for package in packages():
            print(f"Validated source allowlist: {package}")
        ET.parse(ROOT / "obs/project.xml")
    elif args.command == "verify":
        verify(args.package, args.tag, args.destination)
    else:
        client = Client(os.environ.get("OBS_CREDENTIALS_FILE"))
        if args.command == "bootstrap":
            bootstrap(client)
        elif args.command == "publish":
            trusted_key()
            publish(client)
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

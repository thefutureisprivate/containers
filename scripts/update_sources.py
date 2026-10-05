#!/usr/bin/env python3
"""Extend a Dependabot release PR with pinned sources for Alpine rebuilds.

Downloads and hashes source inputs only. All compilation happens in OBS.
Run this on the PR branch before merging a source-rebuilt application update.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "containers/obs-service-container_policy"))
from policy import PIN, assets, crate_assets

REPOSITORIES = {
    "kanidm": ("registry-1.docker.io/kanidm/server", "kanidm/kanidm"),
    "kanidm-radius": ("registry-1.docker.io/kanidm/radius", "kanidm/kanidm"),
    "matrix-authentication-service": ("ghcr.io/element-hq/matrix-authentication-service",
                                      "element-hq/matrix-authentication-service"),
    "openthread-border-router": ("registry-1.docker.io/openthread/border-router", "openthread/ot-br-posix"),
}


def update(name):
    directory = ROOT / "containers" / name
    watch = (directory / "upstream/Dockerfile").read_text()
    match = PIN.fullmatch(watch.strip())
    registry, repository = REPOSITORIES[name]
    if not match or match[1] != registry or not re.fullmatch(r"v?\d+\.\d+\.\d+", match[2]):
        raise ValueError("Release watch must pin the expected upstream repository, version and digest")
    reference = watch.strip().removeprefix("FROM ")
    manifest = subprocess.check_output(["skopeo", "--command-timeout=120s", "inspect", "--raw", "docker://" + reference])
    if hashlib.sha256(manifest).hexdigest() != match[3]:
        raise ValueError("Registry manifest differs from the PR's immutable digest")
    version = match[2].removeprefix("v")
    tag = "v" + version
    prefix = f"https://github.com/{repository}"
    urls = {"upstream.tar.gz": f"{prefix}/archive/refs/tags/{tag}.tar.gz"}
    if name == "openthread-border-router":
        urls["upstream.tar.gz"] = f"{prefix}/releases/download/{tag}/ot-br-posix-{tag}.tar.gz"
    elif name == "matrix-authentication-service":
        urls["mas-release.tar.gz"] = f"{prefix}/releases/download/{tag}/mas-cli-x86_64-linux.tar.gz"
    pinned = {}
    with tempfile.TemporaryDirectory(prefix="obs-source-inputs-") as tmp:
        for filename, url in urls.items():
            path = Path(tmp) / filename
            with urllib.request.urlopen(url, timeout=300) as response, path.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            with tarfile.open(path) as archive:
                names = archive.getnames()
                if filename == "upstream.tar.gz" and name != "openthread-border-router":
                    manifest_name = next(n for n in names if n.count("/") == 1 and n.endswith("/Cargo.toml"))
                    cargo = tomllib.loads(archive.extractfile(manifest_name).read().decode())
                    actual = cargo["workspace"]["package"]["version"]
                    if actual != version:
                        raise ValueError("Source archive version differs from the requested release")
                    lock_name = manifest_name.removesuffix("Cargo.toml") + "Cargo.lock"
                    pinned.update(crate_assets(tomllib.loads(archive.extractfile(lock_name).read().decode())))
                if filename == "mas-release.tar.gz" and not any(n.endswith("share/manifest.json") for n in names):
                    raise ValueError("MAS release is missing its frontend assets")
            pinned[filename] = {"url": url, "sha256": hashlib.file_digest(path.open("rb"), "sha256").hexdigest()}
    # Do not touch files until every input has downloaded and passed validation.
    declarations = "".join(f"#!RemoteAsset: {v['url']} sha256:{v['sha256']} {k}\n" for k, v in pinned.items())
    updated = {}
    for filename in ("Containerfile", "Dockerfile"):
        content = (directory / filename).read_text()
        if {k for k in assets(content) if not k.startswith("crate-")} != set(urls):
            raise ValueError("Unexpected source asset layout; review the recipe before updating")
        updated[filename] = declarations + "\n".join(line for line in content.splitlines()
                                                    if not line.startswith("#!RemoteAsset:")) + "\n"
    services = ET.parse(directory / "_service")
    download = services.getroot().find("service[@name='download_url']")
    if download is not None:
        download.find("param[@name='path']").text = urls["upstream.tar.gz"].removeprefix("https://github.com/")
    ET.indent(services)
    updated["_service"] = ET.tostring(services.getroot(), encoding="unicode") + "\n"
    updated["source-lock.json"] = json.dumps({"version": version, "upstream": reference, "assets": pinned}, indent=2) + "\n"
    for filename, content in updated.items():
        (directory / filename).write_text(content)
    print(f"Pinned {name} {version}; review and commit the source-input changes in this PR.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="+", choices=[*REPOSITORIES, "synapse"])
    for name in parser.parse_args().packages:
        if name == "synapse":
            from update_synapse_sources import update as update_synapse
            update_synapse()
        else:
            update(name)

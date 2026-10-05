#!/usr/bin/env python3
"""Resolve Synapse's Alpine Python inputs; OBS downloads and builds the result."""
import concurrent.futures
import email
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "containers/obs-service-container_policy"))
from policy import PIN


def pin_download(path):
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            metadata = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
            metadata = archive.read(metadata)
    else:
        with tarfile.open(path) as archive:
            member = next(m for m in archive if m.name.count("/") == 1 and m.name.endswith("/PKG-INFO"))
            metadata = archive.extractfile(member).read()
    fields = email.message_from_bytes(metadata)
    name, version = fields["Name"], fields["Version"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or not re.fullmatch(r"[A-Za-z0-9_.+-]+", version):
        raise ValueError("Invalid Python distribution metadata")
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60) as response:
        release = json.load(response)
    record = next(v for v in release["urls"] if v["filename"] == path.name)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != record["digests"]["sha256"] or not record["url"].startswith("https://files.pythonhosted.org/"):
        raise ValueError("Python package differs from its published PyPI checksum")
    return path.name, {"url": record["url"], "sha256": digest}, f"{name}=={version} --hash=sha256:{digest}\n"


def write_pins(downloads):
    directory = ROOT / "containers/synapse"
    requirement = (directory / "requirements.txt").read_text().strip()
    match = re.fullmatch(r"matrix-synapse\[oidc,redis,url_preview\]==(\d+\.\d+\.\d+)", requirement)
    if not match:
        raise ValueError("Pin a Synapse release and its reviewed feature set")
    version = match[1]
    references = list(dict.fromkeys(PIN.findall((directory / "Containerfile").read_text())))
    if len(references) != 1:
        raise ValueError("Expected one pinned Alpine Python base")
    image, tag, digest = references[0]
    base = f"{image}:{tag}@sha256:{digest}"
    files = sorted(p for p in Path(downloads).iterdir() if p.name.endswith((".whl", ".tar.gz")))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        pins = list(pool.map(pin_download, files))
    if not any(n.startswith("matrix_synapse-" + version + "-") for n, _, _ in pins):
        raise ValueError("Downloaded Synapse version differs from requirements.txt")
    requirements = "".join(sorted(line for _, _, line in pins))
    assets = {name: pin for name, pin, _ in pins}
    declarations = "".join(f"#!RemoteAsset: {p['url']} sha256:{p['sha256']} {name}\n" for name, p in assets.items())
    outputs = {}
    for filename in ("Containerfile", "Dockerfile"):
        content = (directory / filename).read_text()
        outputs[filename] = declarations + "\n".join(l for l in content.splitlines() if not l.startswith("#!RemoteAsset:")) + "\n"
    outputs["requirements-runtime.txt"] = requirements
    outputs["wheel-lock.json"] = json.dumps({"version": version, "base": base, "assets": assets,
                                             "requirements_sha256": hashlib.sha256(requirements.encode()).hexdigest()}, indent=2) + "\n"
    for name, content in outputs.items():
        (directory / name).write_text(content)
    print(f"Pinned {len(assets)} Python distribution inputs for Synapse {version}.")


def update():
    directory = ROOT / "containers/synapse"
    requirement = (directory / "requirements.txt").read_text().strip()
    references = list(dict.fromkeys(PIN.findall((directory / "Containerfile").read_text())))
    if len(references) != 1 or references[0][0] != "registry-1.docker.io/library/python":
        raise ValueError("Expected the pinned official Alpine Python image")
    image, tag, digest = references[0]
    base = f"{image}:{tag}@sha256:{digest}"
    work = ROOT / ".build/source-downloads"
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="synapse-", dir=work) as tmp:
        command = shlex.split(os.environ.get("PODMAN_COMMAND", "podman"))
        subprocess.run(command + ["run", "--rm", "--userns=keep-id", f"--user={os.getuid()}:{os.getgid()}",
            "--env=HOME=/tmp", "--volume", tmp + ":/downloads:Z", "--entrypoint=python3", base,
            "-m", "pip", "download", "--only-binary=:all:", "--no-binary=zope-interface", "--dest=/downloads",
            requirement, "psycopg2-binary", "setuptools", "wheel"], check=True)
        write_pins(tmp)


if __name__ == "__main__":
    update()

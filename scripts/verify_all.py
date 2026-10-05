#!/usr/bin/env python3
"""Verify OBS-published images, their Git provenance and effective runtime files."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time
import xml.etree.ElementTree as ET

import obs

sys.path.insert(0, str(obs.ROOT / "containers/obs-service-container_policy"))
from policy import archive_config, audit_rootfs, audit_runtime, images, podman, recipe


def expected_provenance(name, commit):
    directory = obs.ROOT / "containers" / name
    _, reference, _ = recipe(directory)
    inputs = {filename: hashlib.sha256((directory / filename).read_bytes()).hexdigest()
              for filename in ("Containerfile", "LICENSE", "NOTICE") if (directory / filename).is_file()}
    return {"builder": "Open Build Service", "package": name, "upstream": reference,
            "platform": "linux/amd64", "git_commit": commit,
            "inputs_sha256": inputs, "runtime_user": images()[name]["user"]}


def verify_runtime(directory, name, commit):
    # Only convert the bytes already accepted by the signature verifier.
    archive_path = directory.parent / "image.tar"
    subprocess.run(["skopeo", "copy", "--remove-signatures", f"dir:{directory}",
                    f"docker-archive:{archive_path}"], check=True)
    with tarfile.open(archive_path) as archive:
        _, config, config_id = archive_config(archive)
    audit_runtime(name, config["config"], images()[name])
    podman("load", "--input", str(archive_path))
    container = podman("create", "--pull=never", "--network=none", "--image-volume=ignore",
                       "--entrypoint=/not-executed", "sha256:" + config_id, capture=True).strip()
    try:
        path = directory.parent / "rootfs.tar"
        podman("export", "--output", str(path), container)
        audit_rootfs(path, name, images()[name])
        with tarfile.open(path) as archive:
            actual = json.load(archive.extractfile("usr/share/obs-container/provenance.json"))
        for key, value in expected_provenance(name, commit).items():
            if actual.get(key) != value:
                raise ValueError(f"{name}: signed provenance differs from this Git checkout ({key})")
    finally:
        podman("rm", container)


def verify_all(timeout):
    client = obs.Client()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=obs.ROOT, text=True).strip()
    pending = set(images())
    deadline = time.monotonic() + timeout
    while pending and time.monotonic() < deadline:
        results = ET.fromstring(client.request("GET", f"/build/{obs.project()}/_result"))
        repository = results.find(f"result[@repository='{obs.REPOSITORY}'][@arch='x86_64']")
        if repository is not None and repository.get("state") == "published" and repository.findtext("scminfo") == commit:
            for name in sorted(pending.copy()):
                status = repository.find(f"status[@package='{name}']")
                if status is None or status.get("code") != "succeeded":
                    continue
                path = f"/build/{obs.project()}/{obs.REPOSITORY}/x86_64/{name}"
                binaries = ET.fromstring(client.request("GET", path))
                info_files = [b.get("filename") for b in binaries if b.get("filename", "").endswith(".containerinfo")]
                if len(info_files) != 1:
                    raise ValueError(f"{name}: expected one OBS container info file")
                info = json.loads(client.request("GET", path + "/" + info_files[0]))
                _, _, version = recipe(obs.ROOT / "containers" / name)
                tags = [tag.rsplit(":", 1)[-1] for tag in info["tags"]]
                tag = next(tag for tag in tags if tag.startswith(version + "-"))
                try:
                    with tempfile.TemporaryDirectory(prefix="obs-release-") as tmp:
                        directory = Path(tmp) / "verified"
                        obs.verify(name, tag, directory)
                        verify_runtime(directory, name, commit)
                except subprocess.CalledProcessError:
                    # Registry publication and the detached signature store can lag.
                    continue
                pending.remove(name)
                print(f"Verified signed OBS build and Git provenance: {name}:{tag}", flush=True)
        if pending:
            print("Waiting for signed OBS publication: " + ", ".join(sorted(pending)), flush=True)
            time.sleep(min(30, max(0, deadline - time.monotonic())))
    if pending:
        raise TimeoutError("OBS publication/verification incomplete: " + ", ".join(sorted(pending)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=1800)
    verify_all(parser.parse_args().timeout)

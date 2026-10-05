#!/usr/bin/env python3
"""Verify OBS-published images, their Git provenance and effective runtime files."""
import argparse
from functools import lru_cache
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time
import xml.etree.ElementTree as ET

import obs

sys.path.insert(0, str(obs.ROOT / "containers/obs-service-container_policy"))
from policy import INPUT_FILES, archive_config, assets, audit_rootfs, audit_runtime, images, podman, recipe


def rendered_allocator_spec(spec, release):
    """Reproduce the two metadata edits OBS makes to this RPM build recipe."""
    if not re.fullmatch(r"\d+\.\d+", release) or re.search(r"^VCS:", spec, re.M):
        raise ValueError("Unexpected allocator RPM metadata")
    vcs = "https://github.com/thefutureisprivate/containers?subdir=containers/hardened-malloc#main"
    rendered, names = re.subn(r"^(Name:[^\n]*\n)", lambda match: match[1] + "VCS: " + vcs + "\n", spec, flags=re.M)
    rendered, releases = re.subn(r"^(Release:[ \t]*)\S+[ \t]*$", lambda match: match[1] + release,
                                rendered, flags=re.M)
    if names != 1 or releases != 1:
        raise ValueError("Expected one allocator RPM name and release")
    return rendered.encode()


@lru_cache(maxsize=1)
def expected_allocator_build():
    directory = obs.ROOT / "containers/hardened-malloc"
    spec = (directory / "obs-hardened-malloc.spec").read_text()
    version = re.search(r"^Version:\s+(\S+)", spec, re.M)[1]
    client = obs.Client()
    path = f"/build/{obs.project()}/tooling/x86_64/hardened-malloc"
    history = ET.fromstring(client.request("GET", path + "/_history", query={"limit": "1"})).find("entry")
    buildinfo = ET.fromstring(client.request("GET", path + "/_buildinfo"))
    if history is None or history.get("srcmd5") != buildinfo.findtext("srcmd5"):
        raise ValueError("Shared allocator build is not current")
    release = re.fullmatch(re.escape(version) + r"-(\d+)", history.get("versrel", ""))
    if release is None:
        raise ValueError("Shared allocator build version differs from Git")
    compiled_spec = rendered_allocator_spec(spec, release[1] + "." + history.get("bcnt", ""))
    pins = re.findall(r"^#!RemoteAsset: \S+ sha256:([0-9a-f]{64})$", spec, re.M)
    hashes = {f: hashlib.sha256((directory / f).read_bytes()).hexdigest()
              for f in ("allocator-check.c", "manifest.py")}
    hashes["obs-hardened-malloc.spec"] = hashlib.sha256(compiled_spec).hexdigest()
    return {
        "builder": "Open Build Service", "version": version,
        "source_sha256": pins[0], "musl_headers_sha256": pins[1],
        "configuration": {"variant": "default", "native": False, "cxx_allocator": False},
        "recipe_sha256": hashes,
    }


def expected_provenance(name, commit):
    directory = obs.ROOT / "containers" / name
    content, reference, _ = recipe(directory)
    inputs = {filename: hashlib.sha256((directory / filename).read_bytes()).hexdigest()
              for filename in INPUT_FILES if (directory / filename).is_file()}
    policy_dir = obs.ROOT / "containers/obs-service-container_policy"
    policy_hashes = {filename: hashlib.sha256((policy_dir / filename).read_bytes()).hexdigest()
                     for filename in ("policy.py", "smoke.py", "images.json")}
    return {"builder": "Open Build Service", "package": name, "upstream": reference,
            "platform": "linux/amd64", "git_commit": commit,
            "inputs_sha256": inputs, "policy_sha256": policy_hashes,
            "assets": assets(content),
            "runtime_user": images()[name]["user"]}


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
        if images()[name]["allocator"] == "musl":
            for key, value in expected_allocator_build().items():
                if actual["allocator"]["build"].get(key) != value:
                    raise ValueError(f"{name}: shared allocator provenance differs from Git ({key})")
    finally:
        podman("rm", container)


def verify_all(timeout):
    client = obs.Client()
    pending = set(images())
    deadline = time.monotonic() + timeout
    while pending and time.monotonic() < deadline:
        results = ET.fromstring(client.request("GET", f"/build/{obs.project()}/_result"))
        repository = results.find(f"result[@repository='{obs.REPOSITORY}'][@arch='x86_64']")
        if repository is not None and repository.get("state") == "published":
            for name in sorted(pending.copy()):
                status = repository.find(f"status[@package='{name}']")
                if status is None or status.get("code") != "succeeded":
                    continue
                path = f"/build/{obs.project()}/{obs.REPOSITORY}/x86_64/{name}"
                buildinfo = ET.fromstring(client.request("GET", path + "/_buildinfo"))
                history = ET.fromstring(client.request("GET", path + "/_history", query={"limit": "1"}))
                built = history.find("entry")
                if built is None or built.get("srcmd5") != buildinfo.findtext("srcmd5"):
                    continue
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
                        # SCM bridge records the last Git change to each package,
                        # which can precede the project branch's current HEAD.
                        recipe_commit = subprocess.check_output(
                            ["git", "log", "-1", "--format=%H", "--", f"containers/{name}"],
                            cwd=obs.ROOT, text=True).strip()
                        verify_runtime(directory, name, recipe_commit)
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

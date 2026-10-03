#!/usr/bin/env python3
"""Wait for the submitted source revisions, then verify their signed images."""
import argparse
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
import xml.etree.ElementTree as ET

import obs
from prepare import images, recipe


def embedded_provenance(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    result = None
    for layer in manifest["layers"]:
        path = directory / layer["digest"].split(":", 1)[1]
        with tarfile.open(path) as archive:
            for member in archive:
                if member.name.removeprefix("./") == "usr/share/obs-container/provenance.json" and member.isfile():
                    result = archive.extractfile(member).read()
    return result


def verify_all(timeout):
    client = obs.Client()
    pending = {}
    for name in images():
        revision = ET.fromstring(client.request("GET", obs.source_path(name)))
        pending[name] = revision.get("srcmd5")
    deadline = time.monotonic() + timeout
    while pending and time.monotonic() < deadline:
        results = ET.fromstring(client.request("GET", f"/build/{obs.project()}/_result"))
        repository = next((r for r in results if r.get("repository") == obs.REPOSITORY and r.get("arch") == "x86_64"), None)
        if repository is not None and repository.get("state") == "published":
            for name, expected_revision in list(pending.items()):
                status = repository.find(f"status[@package='{name}']")
                if status is None or status.get("code") != "succeeded":
                    continue
                history = ET.fromstring(client.request("GET", f"/build/{obs.project()}/{obs.REPOSITORY}/x86_64/{name}/_history", query={"limit": "1"}))
                entry = history.find("entry")
                if entry is None or entry.get("srcmd5") != expected_revision:
                    continue
                _, _, version = recipe(name)
                release = entry.attrib["versrel"].rsplit("-", 1)[1] + "." + entry.attrib["bcnt"]
                tag = f"{version}-{release}"
                try:
                    with tempfile.TemporaryDirectory(prefix="obs-release-") as tmp:
                        directory = Path(tmp) / "verified"
                        obs.verify(name, tag, directory)
                        expected = (obs.ROOT / ".build/obs" / name / "provenance.json").read_bytes()
                        if embedded_provenance(directory) != expected:
                            raise ValueError(f"{name}: signed image provenance does not match this checkout's prepared sources")
                except subprocess.CalledProcessError:
                    # Registry publication and its signature store may lag OBS.
                    continue
                del pending[name]
        if pending:
            print("Waiting for signed OBS publication: " + ", ".join(pending), flush=True)
            time.sleep(min(30, max(0, deadline - time.monotonic())))
    if pending:
        raise TimeoutError("OBS publication/verification incomplete: " + ", ".join(pending))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=1800)
    verify_all(parser.parse_args().timeout)

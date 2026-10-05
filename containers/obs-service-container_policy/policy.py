"""OBS input and runtime policy. Executed inside the isolated OBS build VM."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import tarfile
import tempfile
import xml.etree.ElementTree as ET
import zipfile

CATALOG = Path(__file__).with_name("images.json")
PIN = re.compile(r"^FROM ([a-z0-9./_-]+):([A-Za-z0-9_.-]+)@sha256:([0-9a-f]{64})(?: AS [a-z][a-z0-9_-]*)?$", re.M)
ASSET = re.compile(r"^#!RemoteAsset: (https://github.com/[A-Za-z0-9_./-]+) sha256:([0-9a-f]{64}) ([A-Za-z0-9][A-Za-z0-9_.-]*)$", re.M)
INPUT_FILES = ("Containerfile", "LICENSE", "NOTICE", "enable-webui.py", "nginx.conf",
               "default.conf", "entrypoint.sh", "src/go.mod", "src/go.sum", "src/tools.go",
               "_service", "source-lock.json", "upstream/Dockerfile", "requirements.txt",
               "package.json", "package-lock.json", "build.sh")
ALLOCATOR = Path("/usr/lib64/obs-hardened-malloc")
PRELOAD = "/usr/local/lib/libhardened_malloc.so"


def assets(content):
    declarations = [line for line in content.splitlines() if line.startswith("#!RemoteAsset")]
    matches = ASSET.findall(content)
    if len(declarations) != len(matches) or len({m[2] for m in matches}) != len(matches):
        raise ValueError("Remote assets require unique filenames, HTTPS upstream URLs and SHA256 pins")
    for url, _, filename in matches:
        if filename == "webui.zip" and not re.fullmatch(
                r"https://github.com/stalwartlabs/webui/releases/download/v\d+\.\d+\.\d+/webui.zip", url):
            raise ValueError("Web UI must be a release-and-SHA256-pinned Stalwart bundle")
    return {filename: {"url": url, "sha256": digest} for url, digest, filename in matches}


def verify_assets(directory, content):
    result = assets(content)
    for filename, expected in result.items():
        path = Path(directory) / filename
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
            raise ValueError(f"Remote asset checksum mismatch: {filename}")
        if filename != "webui.zip":
            continue
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if "index.html" not in names or not any(n.endswith(".js") for n in names):
                raise ValueError("Web UI bundle has no index or JavaScript")
            if archive.testzip() is not None:
                raise ValueError("Web UI archive is corrupt")
    return result


def images():
    return json.loads(CATALOG.read_text())


def recipe(directory):
    content = (Path(directory) / "Containerfile").read_text()
    matches = list(dict.fromkeys(PIN.findall(content)))
    if len(matches) != 1:
        raise ValueError("Require exactly one version-and-digest-pinned upstream image")
    registry, tag, digest = matches[0]
    if not re.fullmatch(r"v?\d+\.\d+(?:\.\d+)?(?:-alpine(?:\d+\.\d+)?)?", tag):
        raise ValueError("Use a stable explicit release tag")
    for line in content.splitlines():
        if line.startswith("FROM ") and line != "FROM scratch" and not PIN.fullmatch(line):
            raise ValueError("Unpinned FROM instruction")
    version = tag.removeprefix("v")
    directory = Path(directory)
    if (directory / "source-lock.json").exists():
        lock = json.loads((directory / "source-lock.json").read_text())
        watch = (directory / "upstream/Dockerfile").read_text()
        expected = f"FROM {lock['upstream']}\n"
        if watch != expected:
            raise ValueError("Upstream release changed: run scripts/update_sources.py before merging this PR")
        version = lock["version"]
    if (directory / "requirements.txt").exists():
        match = re.fullmatch(r"matrix-synapse==(\d+\.\d+\.\d+)\n?", (directory / "requirements.txt").read_text())
        if not match:
            raise ValueError("Synapse requires an exact release in requirements.txt")
        version = match[1]
    if (directory / "package.json").exists():
        version = json.loads((directory / "package.json").read_text())["dependencies"]["matter-server"]
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ValueError("Matter server requires an exact npm release")
    if (Path(directory) / "src/go.mod").is_file():
        module = (Path(directory) / "src/go.mod").read_text()
        match = re.search(r"software\.sslmate\.com/src/certspotter v(\d+\.\d+\.\d+)", module)
        if not match:
            raise ValueError("Cert Spotter requires a pinned upstream Go module")
        version = match[1]
    return content, f"{registry}:{tag}@sha256:{digest}", version


def check_recipe(directory, name):
    content, reference, version = recipe(directory)
    if name in ("stalwart", "postgresql") and "-alpine" not in version:
        raise ValueError(f"{name}: keep the reviewed Alpine variant")
    users = re.findall(r"^USER (.+)$", content, re.M)
    if not users or users[-1] != images()[name]["user"]:
        raise ValueError(f"{name}: final USER must be {images()[name]['user']}")
    declaration = (Path(directory) / "Dockerfile").read_text()
    imports = re.findall(r"^FROM (\S+)", declaration, re.M)
    if imports != [reference.split("@")[0]]:
        raise ValueError(f"{name}: Dockerfile import and Containerfile pin must name the same tag")
    if assets(content) != assets(declaration):
        raise ValueError(f"{name}: Dockerfile and Containerfile remote assets differ")
    if name == "stalwart" and not assets(content):
        raise ValueError("Stalwart requires its pinned Web UI bundle")
    allocator = images()[name]["allocator"]
    if allocator in ("musl", "glibc"):
        if f"ENV LD_PRELOAD={PRELOAD}" not in content or "COPY --chmod=0755 allocator-check" not in content:
            raise ValueError(f"{name}: missing shared allocator or loading check")
        if allocator == "glibc" and "COPY --chmod=0644 ld.so.preload /etc/ld.so.preload" not in content:
            raise ValueError(f"{name}: glibc requires global allocator preloading")
    elif allocator != "static-go" or "LD_PRELOAD" in content:
        raise ValueError(f"{name}: unreviewed allocator or ineffective static preload")
    return content, reference, version

def podman(*args, capture=False, merge_stderr=False, timeout=None, input_text=None):
    command = shlex.split(os.environ.get("PODMAN_COMMAND", "podman")) + list(args)
    return subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.STDOUT if merge_stderr else None, timeout=timeout,
                          input=input_text).stdout

def runtime_config(info):
    config = dict(info["Config"])
    for key in ("Healthcheck", "HealthCheck"):
        if info.get(key):
            config["Healthcheck"] = info[key]
    return config

def comparable(field, value):
    if field == "Env":
        return sorted(value or [])
    if field in ("Volumes", "ExposedPorts"):
        return sorted(value or {})
    if field in ("Entrypoint", "Cmd"):
        return value or []
    if field == "WorkingDir":
        return value or "/"
    if field == "Healthcheck" and value:
        return {key: val for key, val in value.items() if val is not None and val != 0}
    return value or None

def audit_runtime(name, config, spec):
    user = config.get("User") or ""
    if not re.fullmatch(r"[1-9]\d*:[1-9]\d*", user) or user != spec["user"]:
        raise ValueError(f"{name}: runtime must use the reviewed non-root UID:GID {spec['user']}")
    if (config.get("Labels") or {}).get("io.containers.capabilities"):
        raise ValueError(f"{name}: image must not request additional capabilities")
    if spec.get("allocator") in ("musl", "glibc"):
        env = dict(item.split("=", 1) for item in config.get("Env", []) if "=" in item)
        if env.get("LD_PRELOAD") != PRELOAD:
            raise ValueError(f"{name}: runtime must preload the shared allocator")

def static_elf(stream):
    """Reject dynamically linked binaries without executing an untrusted ldd."""
    header = stream.read(64)
    if len(header) < 64 or header[:6] != b"\x7fELF\x02\x01":
        raise ValueError("Expected a little-endian ELF64 executable")
    offset = struct.unpack_from("<Q", header, 32)[0]
    size, count = struct.unpack_from("<HH", header, 54)
    if not count or size < 56 or count > 4096:
        raise ValueError("Invalid ELF program header")
    for i in range(count):
        stream.seek(offset + i * size)
        if struct.unpack("<I", stream.read(4))[0] == 3:  # PT_INTERP
            raise ValueError("Scratch executable requires a dynamic loader")

def audit_file_privileges(member, name):
    if (member.isfile() or member.islnk()) and member.mode & 0o6000:
        raise ValueError(f"{name}: setuid/setgid file: {member.name}")
    if any("security.capability" in key for key in member.pax_headers):
        raise ValueError(f"{name}: file capability: {member.name}")

def audit_rootfs(path, name, spec):
    with tarfile.open(path) as archive:
        members = {}
        for member in archive:
            audit_file_privileges(member, name)
            members[member.name.removeprefix("./").rstrip("/")] = member
        for binary in spec["binaries"]:
            member = members.get(binary.lstrip("/"))
            if not member or not member.isfile():
                raise ValueError(f"Missing static executable: {binary}")
            static_elf(archive.extractfile(member))
        if spec["binaries"]:
            if any(p in members for p in ("bin/sh", "bin/busybox", "usr/bin/apt", "sbin/apk")):
                raise ValueError("Unexpected shell/package manager in scratch runtime")
            cert = members.get("etc/ssl/certs/ca-certificates.crt")
            if not cert or not cert.isfile() or not cert.size:
                raise ValueError("Missing TLS CA bundle")
        if name == "stalwart":
            provenance = json.load(archive.extractfile("usr/share/obs-container/provenance.json"))
            expected = provenance["assets"]["webui.zip"]["sha256"]
            bundle = archive.extractfile("usr/share/stalwart/webui.zip")
            if hashlib.file_digest(bundle, "sha256").hexdigest() != expected:
                raise ValueError("Embedded Web UI differs from the verified OBS input")
        if spec.get("runtime") == "alpine":
            release = archive.extractfile("etc/os-release").read().decode()
            if not re.search(r'^ID=[\"]?alpine[\"]?$', release, re.M):
                raise ValueError("Runtime must be Alpine Linux")
            if "lib/ld-musl-x86_64.so.1" not in members:
                raise ValueError("Alpine runtime is missing its musl loader")
            if any(p.endswith("ld-linux-x86-64.so.2") for p in members):
                raise ValueError("Alpine runtime must not contain a glibc loader")
        if spec.get("allocator") in ("musl", "glibc"):
            provenance = json.load(archive.extractfile("usr/share/obs-container/provenance.json"))
            allocator = provenance["allocator"]
            if allocator["libc"] != spec["allocator"]:
                raise ValueError("Wrong allocator libc variant")
            hashes = allocator["build"]["artifacts"][spec["allocator"]]
            for source, target in (("libhardened_malloc.so", PRELOAD),
                                   ("allocator-check", "/usr/local/bin/allocator-check")):
                actual = hashlib.file_digest(archive.extractfile(target.lstrip("/")), "sha256").hexdigest()
                if actual != hashes[source]:
                    raise ValueError("Container allocator differs from the shared OBS build")
            if spec["allocator"] == "glibc":
                if archive.extractfile("etc/ld.so.preload").read().decode().strip() != PRELOAD:
                    raise ValueError("glibc global allocator configuration differs")


def prepare_allocator(name, outdir):
    """Copy a verified artifact from the shared RPM, never compile per image."""
    libc = images()[name]["allocator"]
    if libc == "static-go":
        return {"libc": None, "reason": images()[name]["allocator_note"]}
    build = json.loads((ALLOCATOR / "manifest.json").read_text())
    for filename, target in (("libhardened_malloc.so", "hardened-malloc.so"),
                             ("allocator-check", "allocator-check")):
        source = ALLOCATOR / libc / filename
        if hashlib.sha256(source.read_bytes()).hexdigest() != build["artifacts"][libc][filename]:
            raise ValueError("Shared allocator RPM artifact checksum mismatch")
        shutil.copyfile(source, outdir / target)
    shutil.copyfile(ALLOCATOR / "LICENSE", outdir / "hardened-malloc.LICENSE")
    if libc == "glibc":
        (outdir / "ld.so.preload").write_text(PRELOAD + "\n")
    return {"libc": libc, "build": build,
            "coverage": images()[name].get("allocator_note", "Dynamically linked native malloc allocations")}


def archive_config(archive):
    manifest = json.load(archive.extractfile("manifest.json"))
    if len(manifest) != 1:
        raise ValueError("Expected one imported image per archive")
    entry = manifest[0]
    config_bytes = archive.extractfile(entry["Config"]).read()
    config_id = hashlib.sha256(config_bytes).hexdigest()
    return entry, json.loads(config_bytes), config_id


def layer_digest(stream):
    magic = stream.read(4)
    stream.seek(0)
    if magic[:2] == b"\x1f\x8b":
        stream = gzip.GzipFile(fileobj=stream)
    elif magic == b"\x28\xb5\x2f\xfd":
        # OBS retains compressed registry blobs in its Docker archive. Python
        # 3.13 has no stdlib zstd reader; use the build VM's packaged decoder.
        with tempfile.TemporaryFile() as compressed:
            shutil.copyfileobj(stream, compressed)
            compressed.seek(0)
            with subprocess.Popen(["zstd", "--decompress", "--stdout"], stdin=compressed,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE) as decoder:
                result = hashlib.file_digest(decoder.stdout, "sha256").hexdigest()
                if decoder.wait() != 0:
                    raise ValueError("Invalid zstd image layer")
        return "sha256:" + result
    return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


def verify_import(directory, reference):
    """Tie OBS's verified registry digest to the config and every unpacked layer."""
    directory = Path(directory)
    annotation = ET.parse(directory / "annotation").getroot()
    expected = reference.split("@", 1)[1]
    digests = {annotation.findtext("registry_digest"), annotation.findtext("registry_fatdigest")}
    if expected not in digests:
        raise ValueError("OBS imported a different upstream digest; refusing to build")
    declared = reference.split("@", 1)[0].replace("registry-1.docker.io/", "docker.io/")
    if annotation.findtext("registry_refname") != declared:
        raise ValueError("OBS imported a different upstream repository/tag")
    archives = list(directory.rglob("*.tar"))
    if len(archives) != 1:
        raise ValueError("Expected exactly one OBS-imported upstream archive")
    with tarfile.open(archives[0]) as archive:
        entry, config, config_id = archive_config(archive)
        if annotation.findtext("binaryid", "").removeprefix("sha256:") != config_id:
            raise ValueError("Imported config does not match OBS's registry annotation")
        if config.get("architecture") != "amd64" or config.get("os") != "linux":
            raise ValueError("Only linux/amd64 inputs are permitted")
        if config.get("config", {}).get("OnBuild"):
            raise ValueError("Upstream ONBUILD instructions require explicit review")
        diff_ids = config.get("rootfs", {}).get("diff_ids", [])
        if len(diff_ids) != len(entry["Layers"]):
            raise ValueError("Upstream layer count differs from pinned config")
        for filename, diff_id in zip(entry["Layers"], diff_ids):
            stream = archive.extractfile(filename)
            actual = layer_digest(stream)
            if actual != diff_id:
                raise ValueError(f"Imported layer does not match pinned config: {filename}: {actual} != {diff_id}")
    print(f"Verified OBS registry import: {reference}", flush=True)
    return config_id


def prepare_build(name, outdir):
    directory = Path.cwd()
    content, reference, version = check_recipe(directory, name)
    config_id = verify_import(directory / "containers", reference)
    remote_assets = verify_assets(directory, content)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    allocator = prepare_allocator(name, outdir)
    generated = {}
    if name in ("certspotter", "kanidm", "kanidm-radius", "matrix-authentication-service"):
        vendor_name = "vendor.tar.gz"
        candidates = list(directory.glob("*" + vendor_name))
        if len(candidates) != 1:
            raise ValueError("OBS dependency service must provide exactly one vendor archive")
        generated[vendor_name] = hashlib.sha256(candidates[0].read_bytes()).hexdigest()
        if candidates[0].name != vendor_name:
            shutil.copyfile(candidates[0], outdir / vendor_name)
    info = (directory / "_scmsync.obsinfo").read_text()
    match = re.search(r"^commit: ([0-9a-f]{40,64})$", info, re.M)
    if not match:
        raise ValueError("Missing OBS Git source revision")
    inputs = {filename: hashlib.sha256((directory / filename).read_bytes()).hexdigest()
              for filename in INPUT_FILES if (directory / filename).is_file()}
    policy_hashes = {filename: hashlib.sha256((CATALOG.parent / filename).read_bytes()).hexdigest()
                     for filename in ("policy.py", "smoke.py", "images.json")}
    provenance = {"builder": "Open Build Service", "package": name, "upstream": reference,
                  "platform": "linux/amd64", "git_commit": match[1],
                  "inputs_sha256": inputs, "upstream_config_sha256": config_id,
                  "policy_sha256": policy_hashes,
                  "assets": remote_assets,
                  "generated_sources_sha256": generated,
                  "allocator": allocator,
                  "runtime_user": images()[name]["user"]}
    (outdir / "provenance.json").write_text(json.dumps(provenance, sort_keys=True, indent=2) + "\n")
    # The imported archive has a local tag. It has just been checked against the
    # immutable pin, including the config and uncompressed layer hashes.
    content = content.replace(reference, reference.split("@")[0])
    rendered = (f"#!BuildTag: {name}:{version}-<RELEASE> {name}:{version} {name}:latest\n"
                f"#!BuildName: {name}\n#!BuildVersion: {version.split('-')[0]}\n" + content +
                '\nCOPY provenance.json /usr/share/obs-container/provenance.json\n' +
                'LABEL org.opencontainers.image.source="https://github.com/thefutureisprivate/containers"\n' +
                f'LABEL org.opencontainers.image.version="{version}"\n' +
                f'LABEL org.opencontainers.image.revision="{match[1]}"\n')
    (outdir / "Dockerfile").write_text(rendered)
    for filename in ("Dockerfile", "provenance.json"):
        (outdir / filename).chmod(0o644)
    print(f"Rendered {name}:{version} inside OBS from Git {match[1]}", flush=True)


def check_build():
    sources = Path("/usr/src/packages/SOURCES")
    if not (sources / "Containerfile").exists():
        return
    provenance = json.loads((sources / "provenance.json").read_text())
    name = provenance["package"]
    archives = list(Path("/usr/src/packages/DOCKER").glob("*.tar"))
    if len(archives) != 1:
        raise ValueError("Expected one OBS-built image archive")
    with tarfile.open(archives[0]) as archive:
        _, config, config_id = archive_config(archive)
    audit_runtime(name, config["config"], images()[name])
    os.environ["PODMAN_COMMAND"] = "/usr/lib/build/call-podman --root /"
    podman("load", "--input", str(archives[0]))
    image_id = "sha256:" + config_id
    container = podman("create", "--pull=never", "--network=none", "--image-volume=ignore",
                       "--entrypoint=/not-executed", image_id, capture=True).strip()
    try:
        with tempfile.TemporaryDirectory(prefix="obs-runtime-") as tmp:
            path = Path(tmp) / "rootfs.tar"
            podman("export", "--output", str(path), container)
            audit_rootfs(path, name, images()[name])
            with tarfile.open(path) as archive:
                embedded = archive.extractfile("usr/share/obs-container/provenance.json").read()
            if embedded != (sources / "provenance.json").read_bytes():
                raise ValueError("Built image provenance does not match OBS inputs")
    finally:
        podman("rm", container)
    from smoke import smoke
    smoke(name, image_id)
    print(f"OBS runtime policy and smoke tests passed: {name}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    preparation = sub.add_parser("prepare")
    preparation.add_argument("--name", required=True, choices=list(images()))
    preparation.add_argument("--outdir", required=True)
    sub.add_parser("check-build")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare_build(args.name, args.outdir)
    else:
        check_build()


if __name__ == "__main__":
    main()

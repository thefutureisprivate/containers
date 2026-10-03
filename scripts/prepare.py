#!/usr/bin/env python3
"""Prepare pinned upstream runtimes for network-isolated OBS image builds."""
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

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".build/obs"
RUNTIME_FIELDS = ("Env", "User", "WorkingDir", "Entrypoint", "Cmd", "Volumes", "ExposedPorts", "StopSignal", "Healthcheck")
PIN = re.compile(r"^FROM ([a-z0-9./_-]+):([A-Za-z0-9_.-]+)@sha256:([0-9a-f]{64})(?: AS upstream)?$", re.M)


def images():
    return json.loads((ROOT / "obs/images.json").read_text())


def context_files(name):
    directory = ROOT / "containers" / name
    allowed = ("Dockerfile", "LICENSE", "NOTICE")
    files = {}
    for filename in allowed:
        path = directory / filename
        if path.is_symlink():
            raise ValueError("Symlinked build inputs are not supported")
        if path.is_file():
            files[filename] = path.read_bytes()
    return files


def recipe(name):
    content = (ROOT / "containers" / name / "Dockerfile").read_text()
    match = PIN.search(content)
    if not match or len(PIN.findall(content)) != 1:
        raise ValueError(f"{name}: require one upstream FROM with a version and SHA-256 digest")
    for line in content.splitlines():
        if line.startswith("FROM ") and line != "FROM scratch" and not PIN.fullmatch(line):
            raise ValueError(f"{name}: unpinned FROM")
    registry, tag, digest = match.groups()
    if not re.fullmatch(r"v?\d+\.\d+(?:\.\d+)?(?:-alpine\d+\.\d+)?", tag):
        raise ValueError(f"{name}: use a stable, explicit release tag")
    return content, f"{registry}:{tag}@sha256:{digest}", tag.removeprefix("v")


def podman(*args, capture=False, merge_stderr=False):
    command = shlex.split(os.environ.get("PODMAN_COMMAND", "podman")) + list(args)
    return subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.STDOUT if merge_stderr else None).stdout


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


def audit_rootfs(path, name, spec):
    with tarfile.open(path) as archive:
        members = {m.name.removeprefix("./").rstrip("/"): m for m in archive}
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
            binary = members["usr/local/bin/stalwart"]
            if "SCHILY.xattr.security.capability" not in binary.pax_headers:
                raise ValueError("Stalwart's file capabilities were lost during export")


def render(name, version, config):
    """Translate Docker runtime configuration; reject unsupported instructions."""
    if config.get("OnBuild"):
        raise ValueError("ONBUILD instructions require explicit review")
    lines = [f"#!BuildTag: {name}:{version}-<RELEASE> {name}:{version} {name}:latest",
             f"#!BuildName: {name}", f"#!BuildVersion: {version.split('-')[0]}",
             "FROM scratch", "ADD rootfs.tar.gz /",
             "COPY provenance.json /usr/share/obs-container/provenance.json"]
    for entry in config.get("Env") or []:
        key, value = entry.split("=", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError("Invalid environment variable name")
        if any(char in value for char in "\r\n\x00"):
            raise ValueError("Multiline environment values need explicit review")
        # Dockerfile double-quoted values expand dollars unless escaped.
        lines.append(f"ENV {key}=" + json.dumps(value, ensure_ascii=False).replace(r"\t", "\t").replace("$", r"\$"))
    for key, value in sorted((config.get("Labels") or {}).items()):
        lines.append("LABEL " + json.dumps(key) + "=" + json.dumps(value).replace("$", r"\$"))
    lines += [f'LABEL org.opencontainers.image.source="https://github.com/thefutureisprivate/containers"',
              f'LABEL org.opencontainers.image.version="{version}"']
    ports = sorted(config.get("ExposedPorts") or {})
    for port in ports:
        if not re.fullmatch(r"\d+/(?:tcp|udp|sctp)", port):
            raise ValueError("Invalid exposed port")
    if ports:
        # Older Buildah versions lose one protocol when a port is exposed in
        # separate instructions. Preserve TCP+UDP together in one instruction.
        lines.append("EXPOSE " + " ".join(ports))
    for key, instruction in (("WorkingDir", "WORKDIR"), ("User", "USER"), ("StopSignal", "STOPSIGNAL")):
        value = config.get(key)
        if value:
            if not re.fullmatch(r"[A-Za-z0-9_/:.\-]+", value):
                raise ValueError(f"Unsupported {key}: review before publication")
            lines.append(instruction + " " + value)
    if config.get("Volumes"):
        lines.append("VOLUME " + json.dumps(sorted(config["Volumes"])))
    if config.get("Shell"):
        lines.append("SHELL " + json.dumps(config["Shell"]))
    health = config.get("Healthcheck")
    if health:
        test = health.get("Test", [])
        if test == ["NONE"]:
            lines.append("HEALTHCHECK NONE")
        elif test:
            flags = []
            for field, flag in (("Interval", "interval"), ("Timeout", "timeout"), ("StartPeriod", "start-period"), ("StartInterval", "start-interval")):
                if health.get(field):
                    flags.append(f"--{flag}={int(health[field])}ns")
            if health.get("Retries"):
                flags.append(f"--retries={int(health['Retries'])}")
            command = json.dumps(test[1:]) if test[0] == "CMD" else test[1]
            if "\n" in command or test[0] not in ("CMD", "CMD-SHELL"):
                raise ValueError("Unsupported healthcheck")
            lines.append("HEALTHCHECK " + " ".join(flags) + " CMD " + command)
    for key in ("Entrypoint", "Cmd"):
        if config.get(key) is not None:
            lines.append(key.upper() + " " + json.dumps(config[key]))
    return "\n".join(lines) + "\n"


def prepare(name):
    spec = images()[name]
    content, reference, version = recipe(name)
    OUT.mkdir(parents=True, exist_ok=True)
    tag = f"localhost/obs-prepared/{name}:test"
    with tempfile.TemporaryDirectory(prefix=f"{name}-", dir=OUT.parent) as tmp:
        tmp = Path(tmp)
        context = tmp / "context"
        context.mkdir()
        inputs = context_files(name)
        for filename, data in inputs.items():
            (context / filename).write_bytes(data)
        podman("pull", "--platform=linux/amd64", reference)
        podman("build", "--platform=linux/amd64", "--format=docker", "--pull=never", "--network=none",
               "--tag", tag, str(context))
        shutil.rmtree(context)
        info = json.loads(podman("image", "inspect", tag, capture=True))[0]
        if info["Architecture"] != "amd64" or info["Os"] != "linux":
            raise ValueError("Only linux/amd64 is configured in OBS")
        config = runtime_config(info)
        container = podman("create", "--pull=never", "--network=none", "--image-volume=ignore",
                           "--entrypoint=/not-executed", tag, capture=True).strip()
        try:
            podman("export", "--output", str(tmp / "rootfs.tar"), container)
        finally:
            podman("rm", container)
        audit_rootfs(tmp / "rootfs.tar", name, spec)
        with (tmp / "rootfs.tar").open("rb") as source, (tmp / "rootfs.tar.gz").open("wb") as target:
            with gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0) as compressed:
                shutil.copyfileobj(source, compressed)
        (tmp / "rootfs.tar").unlink()
        (tmp / "upstream.Dockerfile").write_text(content)
        (tmp / "Dockerfile").write_text(render(name, version, config))
        with (tmp / "rootfs.tar.gz").open("rb") as archive:
            rootfs_hash = hashlib.file_digest(archive, "sha256").hexdigest()
        provenance = {"package": name, "upstream": reference, "platform": "linux/amd64",
                      "inputs_sha256": {key: hashlib.sha256(value).hexdigest() for key, value in inputs.items()},
                      "recipe_sha256": hashlib.sha256(content.encode()).hexdigest(),
                      "rootfs_sha256": rootfs_hash,
                      "dockerfile_sha256": hashlib.sha256((tmp / "Dockerfile").read_bytes()).hexdigest(),
                      "runtime_config": config}
        (tmp / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
        # Check the exact generated recipe that OBS will build, including xattrs.
        podman("build", "--format=docker", "--pull=never", "--network=none", "--tag", tag, str(tmp))
        rebuilt = runtime_config(json.loads(podman("image", "inspect", tag, capture=True))[0])
        for field in RUNTIME_FIELDS:
            expected, actual = comparable(field, config.get(field)), comparable(field, rebuilt.get(field))
            if expected != actual:
                raise ValueError(f"{name}: offline recipe changed runtime configuration ({field}): {expected!r} -> {actual!r}")
        target = OUT / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(tmp, target)
    print(f"Prepared {name}:{version} for OBS", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="*", choices=list(images()) + ["all"])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    names = list(images()) if not args.packages or "all" in args.packages else args.packages
    for name in names:
        if args.check:
            recipe(name)
            print(f"Validated immutable upstream recipe: {name}")
        else:
            prepare(name)


if __name__ == "__main__":
    main()

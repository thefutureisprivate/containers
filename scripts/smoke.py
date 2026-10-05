#!/usr/bin/env python3
"""Exercise the generated OBS runtime, never a mutable upstream tag."""
import argparse
import json
import secrets
import subprocess
import time

from prepare import audit_runtime, images, podman, runtime_config


def audit_processes(container):
    # Podman reads these from /proc, including for images without ps or a shell.
    output = podman("top", container, "user", "capbnd", "capeff", "capprm", capture=True)
    rows = [line.split() for line in output.splitlines()[1:] if line.strip()]
    if not rows:
        raise ValueError("No running processes to audit")
    for row in rows:
        if len(row) != 4 or row[0] in ("root", "0") or any(cap != "none" for cap in row[1:]):
            raise ValueError("Container process has root identity or capabilities: " + " ".join(row))


def wait_for_command(container, *command):
    failure = ""
    for _ in range(60):
        try:
            return podman("exec", container, *command, capture=True, merge_stderr=True)
        except subprocess.CalledProcessError as error:
            failure = (error.stdout or "").strip()[-1000:]
            state = json.loads(podman("inspect", "--format={{json .State}}", container, capture=True))
            if not state.get("Running"):
                break
            time.sleep(1)
    # Bootstrap logs may contain generated credentials. Do not print them.
    raise ValueError("Container initialization/readiness failed: " + failure)


def smoke(name):
    spec = images()[name]
    image = f"localhost/obs-prepared/{name}:test"
    info = json.loads(podman("image", "inspect", image, capture=True))[0]
    audit_runtime(name, runtime_config(info), spec)
    common = ["--pull=never", "--network=none", "--read-only", "--cap-drop=ALL",
              "--security-opt=no-new-privileges", "--pids-limit=128", "--memory=512m",
              "--tmpfs=/tmp:rw,nosuid,nodev,size=64m"]
    executable, *args = spec["smoke"]
    output = podman("run", "--rm", *common, "--entrypoint", executable, image, *args, capture=True, merge_stderr=True)
    if not output.strip():
        raise ValueError(f"{name}: version command produced no output")
    print(output.strip(), flush=True)
    if name == "kanidm-radius":
        podman("run", "--rm", *common, "--entrypoint=/usr/local/bin/kanidm_radiusd", image, "--help")
    if name == "postgresql":
        # Check real volume copy-up permissions separately from database fsync.
        podman("run", "--rm", *common, "--entrypoint=sh", image, "-ec",
               'mkdir -p "$PGDATA"; test -w "$PGDATA"; '
               'test "$(stat -c %u:%g "$PGDATA")" = "$(id -u):$(id -g)"')
        # A bounded tmpfs avoids host disk writeback delays in initdb. The
        # entrypoint creates PGDATA as its default user, without a root phase.
        password = secrets.token_hex(24)
        flags = common + ["--tmpfs=/var/lib/postgresql:rw,mode=1777,size=192m",
                          "--tmpfs=/run/postgresql:rw,mode=1777,size=8m",
                          "--env", "POSTGRES_PASSWORD=" + password]
        container = podman("run", "--detach", *flags, image, capture=True).strip()
        try:
            # The temporary initialization server has no TCP listener. This
            # query waits for the final server, not the transient initdb phase.
            result = wait_for_command(container, "sh", "-c",
                                      'PGPASSWORD="$POSTGRES_PASSWORD" exec psql -h 127.0.0.1 -U postgres -Atc "SELECT 42"')
            if result.strip() != "42":
                raise ValueError("PostgreSQL query failed")
            audit_processes(container)
        except ValueError:
            # This fresh database has only the disposable password generated
            # above. Redact it before printing initialization diagnostics.
            log = podman("logs", container, capture=True, merge_stderr=True)
            print(log.replace(password, "[redacted]")[-8000:], flush=True)
            podman("top", container, "user", "comm", "etime")
            raise
        finally:
            podman("rm", "--force", "--volumes", container)
    elif name == "stalwart":
        # Fresh anonymous volumes test bootstrap permissions at both declared
        # paths. The initial management listener uses unprivileged port 8080.
        container = podman("run", "--detach", *common, image, capture=True).strip()
        try:
            wait_for_command(container, "curl", "--fail", "--silent", "--output", "/dev/null",
                             "http://127.0.0.1:8080/healthz/live")
            audit_processes(container)
        finally:
            podman("rm", "--force", "--volumes", container)
    elif name in ("prometheus", "alertmanager", "blackbox-exporter", "postgres-exporter", "node-exporter"):
        flags = common.copy()
        if name in ("prometheus", "alertmanager"):
            flags += [f"--tmpfs=/{name}:rw,mode=1777,size=64m"]
        if name == "postgres-exporter":
            flags += ["--env", "DATA_SOURCE_NAME=postgresql://test@127.0.0.1/test?sslmode=disable"]
        command = (["--config.file=/etc/alertmanager/alertmanager.yml", "--storage.path=/alertmanager", "--cluster.listen-address="]
                   if name == "alertmanager" else [])
        container = podman("run", "--detach", *flags, image, *command, capture=True).strip()
        try:
            time.sleep(3)
            state = json.loads(podman("inspect", "--format={{json .State}}", container, capture=True))
            if not state.get("Running"):
                raise ValueError(f"{name} failed to start: " + podman("logs", container, capture=True))
            audit_processes(container)
            if name == "prometheus":
                podman("exec", container, "/bin/promtool", "check", "config", "/etc/prometheus/prometheus.yml")
            elif name == "alertmanager":
                podman("exec", container, "/bin/amtool", "check-config", "/etc/alertmanager/alertmanager.yml")
        finally:
            podman("rm", "--force", "--volumes", container)
    print(f"Smoke test passed: {name}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="*", choices=list(images()) + ["all"])
    args = parser.parse_args()
    for name in (list(images()) if not args.packages or "all" in args.packages else args.packages):
        smoke(name)

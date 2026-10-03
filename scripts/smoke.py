#!/usr/bin/env python3
"""Exercise the generated OBS runtime, never a mutable upstream tag."""
import argparse
import json
import secrets
import time

from prepare import images, podman


def smoke(name):
    spec = images()[name]
    image = f"localhost/obs-prepared/{name}:test"
    common = ["--pull=never", "--network=none", "--read-only", "--cap-drop=ALL",
              "--security-opt=no-new-privileges", "--pids-limit=128", "--memory=512m",
              "--tmpfs=/tmp:rw,nosuid,nodev,size=64m"]
    if name == "stalwart":
        common += ["--cap-add=NET_BIND_SERVICE"]
    executable, *args = spec["smoke"]
    output = podman("run", "--rm", *common, "--entrypoint", executable, image, *args, capture=True, merge_stderr=True)
    if not output.strip():
        raise ValueError(f"{name}: version command produced no output")
    print(output.strip(), flush=True)
    if name == "kanidm-radius":
        podman("run", "--rm", *common, "--entrypoint=/usr/local/bin/kanidm_radiusd", image, "--help")
    if name == "postgresql":
        # Official PostgreSQL initializes as root and then drops privileges.
        flags = ["--pull=never", "--network=none", "--read-only", "--memory=512m",
                 "--tmpfs=/var/lib/postgresql:rw,size=192m", "--tmpfs=/var/run/postgresql:rw,size=8m",
                 "--tmpfs=/tmp:rw,size=16m", "--env", "POSTGRES_PASSWORD=" + secrets.token_hex(24)]
        container = podman("run", "--detach", *flags, image, capture=True).strip()
        try:
            for _ in range(60):
                try:
                    result = podman("exec", "--user=postgres", container, "psql", "-U", "postgres", "-Atc", "SELECT 42", capture=True)
                    if result.strip() == "42":
                        break
                except Exception:
                    pass
                time.sleep(1)
            else:
                raise ValueError("PostgreSQL initialization/query failed")
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

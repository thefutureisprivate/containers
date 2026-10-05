"""Smoke-test the image built by OBS before it can be published."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import secrets
import subprocess
import time
import zipfile

from policy import audit_runtime, images, podman, runtime_config


def audit_processes(container):
    # Podman reads these from /proc, including for images without ps or a shell.
    output = podman("top", container, "user", "capbnd", "capeff", "capprm", capture=True)
    rows = [line.split() for line in output.splitlines()[1:] if line.strip()]
    if not rows:
        raise ValueError("No running processes to audit")
    for row in rows:
        if len(row) != 4 or row[0] in ("root", "0") or any(cap != "none" for cap in row[1:]):
            raise ValueError("Container process has root identity or capabilities: " + " ".join(row))


def check_allocator(container):
    podman("exec", container, "/usr/local/bin/allocator-check", "--pid1")


def expansion_smoke(name, image, common):
    """Offline startup checks; hardware and external identity services need deployment tests."""
    if name == "certbot":
        podman("run", "--rm", *common, image, "plugins", "--text",
               "--config-dir=/tmp/config", "--work-dir=/tmp/work", "--logs-dir=/tmp/logs")
        return
    if name == "matrix-authentication-service":
        podman("run", "--rm", *common, image, "config", "--help")
        return
    if name == "python-matter-server":
        podman("run", "--rm", *common, "--entrypoint=python3", image, "-c",
               "import chip.native; chip.native.GetLibraryHandle(); print('Matter native SDK loaded')")
        return
    if name in ("certspotter", "openthread-border-router"):
        return
    flags = common.copy()
    command = []
    if name in ("nginx", "element-web"):
        pass
    elif name == "eclipse-mosquitto":
        flags += ["--entrypoint=sh"]
        command = ["-ec", "printf 'listener 1883 127.0.0.1\\nallow_anonymous true\\npersistence false\\n' > /tmp/smoke.conf; "
                   "exec /usr/sbin/mosquitto -c /tmp/smoke.conf"]
    elif name == "synapse":
        flags += ["--memory=1g", "--tmpfs=/data:rw,mode=1777,size=128m",
                  "--env=SYNAPSE_SERVER_NAME=obs.invalid", "--env=SYNAPSE_REPORT_STATS=no", "--entrypoint=sh"]
        command = ["-ec", "python /start.py generate >/tmp/generate.log 2>&1; exec python /start.py"]
    elif name == "home-assistant":
        flags += ["--memory=2g", "--tmpfs=/config:rw,mode=1777,size=128m", "--entrypoint=sh"]
        command = ["-ec", "printf 'http:\\n' > /config/configuration.yaml; "
                   "exec python3 -P -m homeassistant --config /config --skip-pip"]
    elif name == "vaultwarden":
        flags += ["--tmpfs=/data:rw,mode=1777,size=128m", "--env=ROCKET_WORKERS=2"]
    else:
        raise ValueError("Missing smoke test for " + name)
    container = podman("run", "--detach", *flags, image, *command, capture=True).strip()
    try:
        if name in ("nginx", "element-web"):
            page = wait_for_command(container, "wget", "-qO-", "http://127.0.0.1:8080/")
            if "<html" not in page.lower():
                raise ValueError(name + " did not serve its HTML")
            if name == "element-web":
                config = json.loads(podman("exec", container, "wget", "-qO-", "http://127.0.0.1:8080/config.json", capture=True))
                if not isinstance(config, dict):
                    raise ValueError("Element configuration is not an object")
        elif name == "eclipse-mosquitto":
            wait_for_command(container, "mosquitto_pub", "-h", "127.0.0.1", "-t", "obs-check", "-r", "-m", "42")
            message = podman("exec", container, "mosquitto_sub", "-h", "127.0.0.1", "-t", "obs-check",
                             "-C", "1", "-W", "5", capture=True)
            if message.strip() != "42":
                raise ValueError("MQTT round trip failed")
        elif name == "synapse":
            wait_for_command(container, "python", "-c",
                             "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8008/health').status == 200")
        elif name == "home-assistant":
            wait_for_command(container, "python3", "-c",
                             "import http.client; c=http.client.HTTPConnection('127.0.0.1',8123); c.request('GET','/'); "
                             "assert c.getresponse().status in (200,401,404)")
        elif name == "vaultwarden":
            wait_for_command(container, "curl", "--fail", "--silent", "http://127.0.0.1:8080/alive")
        audit_processes(container)
        check_allocator(container)
    finally:
        podman("rm", "--force", "--volumes", container)


def wait_for_command(container, *command):
    failure = ""
    for _ in range(60):
        try:
            # Keep the SQL/readiness output separate from OBS wrapper notices
            # written to stderr (for example "Unsharing environment").
            return podman("exec", container, *command, capture=True, timeout=5)
        except subprocess.CalledProcessError as error:
            failure = (error.stdout or "").strip()[-1000:]
            state = json.loads(podman("inspect", "--format={{json .State}}", container, capture=True))
            if not state.get("Running"):
                break
            time.sleep(1)
        except subprocess.TimeoutExpired:
            failure = "readiness command exceeded five seconds"
    # Bootstrap logs may contain generated credentials. Do not print them.
    raise ValueError("Container initialization/readiness failed: " + failure)


def stalwart_ui(image, common):
    """Exercise the real management API and serve the pinned UI without a network."""
    sources = Path("/usr/src/packages/SOURCES")
    spec = importlib.util.spec_from_file_location("enable_webui", sources / "enable-webui.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    password = secrets.token_hex(24)
    config = json.dumps({"@type": "RocksDb", "path": "/var/lib/stalwart/ui-test",
                         "cacheSize": 8388608, "bufferSize": 8388608})
    container = podman("run", "--detach", *common,
                       "--env", "STALWART_RECOVERY_MODE=1",
                       "--env", "STALWART_RECOVERY_ADMIN=admin:" + password,
                       "--entrypoint=sh", image, "-ec",
                       'printf "%s" "$1" > /etc/stalwart/config.json; '
                       'exec /usr/local/bin/stalwart --config /etc/stalwart/config.json',
                       "sh", config, capture=True).strip()
    try:
        wait_for_command(container, "curl", "--fail", "--silent", "--output", "/dev/null",
                         "http://127.0.0.1:8080/healthz/live")

        def call(method, arguments):
            data = json.dumps(helper.envelope(method, arguments))
            # Pass the disposable test password through stdin, not an exception's argv.
            curl_config = ('url = "http://127.0.0.1:8080/jmap"\n'
                           f'user = "admin:{password}"\n'
                           'header = "Content-Type: application/json"\n'
                           f'data = {json.dumps(data)}\n')
            output = podman("exec", "-i", container, "curl", "--fail", "--silent", "--config", "-",
                            input_text=curl_config, capture=True, timeout=90)
            return helper.result(json.loads(output), method)

        helper.enable(call)
        # Exercise an unchanged second invocation too: it must refresh the cache.
        helper.enable(call)
        with zipfile.ZipFile(sources / "webui.zip") as bundle:
            for prefix in ("admin", "account"):
                html = podman("exec", container, "curl", "--fail", "--silent",
                              f"http://127.0.0.1:8080/{prefix}/index.html", capture=True)
                if f'<base href="/{prefix}/"' not in html:
                    raise ValueError("Stalwart did not mount the bundled UI")
                scripts = re.findall(r'<script[^>]+src="\./(assets/[^"<>]+\.js)"', html)
                if not scripts:
                    raise ValueError("Web UI HTML has no JavaScript entry point")
                for asset in scripts:
                    actual = podman("exec", container, "curl", "--fail", "--silent",
                                    f"http://127.0.0.1:8080/{prefix}/{asset}", capture=True)
                    if actual != bundle.read(asset).decode():
                        raise ValueError("Served Web UI JavaScript differs from the pinned bundle")
        audit_processes(container)
        print("Bundled Stalwart UI passed: management API, /admin, /account, exact JavaScript, network disabled", flush=True)
    except Exception:
        log = podman("logs", container, capture=True, merge_stderr=True)
        print(log.replace(password, "[redacted]")[-4000:], flush=True)
        raise
    finally:
        podman("rm", "--force", "--volumes", container)


def smoke(name, image):
    spec = images()[name]
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
    if spec["allocator"] in ("glibc", "musl"):
        podman("run", "--rm", *common, "--entrypoint=/usr/local/bin/allocator-check", image)
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
            check_allocator(container)
        except ValueError:
            # This fresh database has only the disposable password generated
            # above. Redact it before printing initialization diagnostics.
            log = podman("logs", container, capture=True, merge_stderr=True)
            print(log.replace(password, "[redacted]")[-8000:], flush=True)
            podman("top", container, "user", "pid", "args", "etime")
            try:
                podman("exec", container, "psql", "-U", "postgres", "-Atc",
                       "SELECT pid, wait_event_type, wait_event, state, query FROM pg_stat_activity", timeout=5)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
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
        stalwart_ui(image, common)
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
    elif name not in ("kanidm", "kanidm-radius"):
        expansion_smoke(name, image, common)
    print(f"Smoke test passed: {name}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", choices=list(images()))
    parser.add_argument("image", help="Already loaded, verified image ID")
    args = parser.parse_args()
    smoke(args.package, args.image)

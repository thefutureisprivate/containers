# Signed OBS containers

Recipes for [home:thefutureisprivate:containers](https://build.opensuse.org/project/show/home:thefutureisprivate:containers), maintained in [thefutureisprivate/containers](https://github.com/thefutureisprivate/containers). OBS builds the final images offline, signs them with its project key, and publishes them to `registry.opensuse.org`.

The application images **repackage official upstream binaries pinned by tag and SHA-256 digest**. They do not independently compile those applications from source.

## Images

All images currently target **linux/amd64**. Append the package name and tag to:

```text
registry.opensuse.org/home/thefutureisprivate/containers/containers/
```

| Package | Version at validation | Runtime |
| --- | --- | --- |
| `kanidm` | 1.11.2 | Upstream scratch, required glibc libraries; UID/GID 65532 |
| `kanidm-radius` | 1.11.2 | Upstream openSUSE/FreeRADIUS/native Kanidm module; UID 497 / GID 496 |
| `stalwart` | 0.16.24-alpine | Official Stalwart Alpine runtime; UID/GID 2000 |
| `prometheus` | 3.15.0 | Scratch, static binaries and CA bundle; UID/GID 65532 |
| `blackbox-exporter` | 0.28.0 | Scratch, static binary and CA bundle; UID/GID 65532 |
| `postgres-exporter` | 0.20.1 | Scratch, static binary and CA bundle; UID/GID 65532 |
| `node-exporter` | 1.12.1 | Scratch, static binary and CA bundle; UID/GID 65532 |
| `alertmanager` | 0.34.1 | Scratch, static binaries and CA bundle; UID/GID 65532 |
| `postgresql` | 18.6-alpine3.24 | Official PostgreSQL Alpine runtime; initialization and server use UID/GID 70 |

The table records the latest validation; **the Dockerfiles are the current version source of truth**. OBS publishes `NAME:VERSION-<RELEASE>`, `NAME:VERSION`, and `NAME:latest`. A pinned upstream digest is an integrity pin, not a verified upstream publisher signature. OBS signs the result under this project's identity.

See [Alpine versus scratch](docs/base-images.md) for the security tradeoffs.

Every image declares a numeric, nonzero runtime UID and GID. Preparation rejects root/implicit users, setuid/setgid files, file capabilities and image labels requesting capabilities. RADIUS privilege helpers are stripped, and Stalwart's `NET_BIND_SERVICE` file capability is removed. These checks also apply to Dependabot PR builds. Build-time `USER 0:0` instructions only modify image files; the final runtime user is unprivileged.

## Dependabot and publication

[Dependabot](.github/dependabot.yml) checks all nine upstream image tags/digests daily and pinned GitHub Actions weekly. Updates arrive as PRs; they are not automatically merged. Kanidm and RADIUS updates are grouped when available together. PostgreSQL major releases require a reviewed PR and a database migration plan.

The [workflow](.github/workflows/containers.yml) runs unit checks, builds each generated offline recipe, and smoke tests the result on PRs. PR jobs have read-only GitHub permissions and no OBS credential. On `main`, after all checks pass, one serialized publisher prepares the contexts, submits complete OBS source revisions, waits for publication, verifies signatures, and checks embedded provenance against its inputs. An older workflow checks for a newer `main` commit before publishing.

**One-time setup:** add the repository Actions secret **`OBS_CREDENTIALS`** in [Settings → Secrets and variables → Actions](https://github.com/thefutureisprivate/containers/settings/secrets/actions). Its value is an OBS credential file, for example:

```json
{"username":"thefutureisprivate","password":"YOUR_OBS_PASSWORD"}
```

The existing `/tmp/obs-creds` format (username/password on separate lines, with an optional leading label) also works. The secret is exposed only to the publication step on `main`, written to a temporary file with mode 600, and removed afterward. Never commit it. Anyone able to change and run a trusted `main` workflow can use its Actions secrets; restrict repository write access and protect `main` as appropriate.

The publication job reports a missing secret explicitly. After adding it, rerun the failed job or use **Run workflow** on `main`.

## Local build and publish

Requirements: Python 3.11+, Make, Podman, GnuPG, Skopeo, working container user namespaces, and storage for the image runtimes. No Python packages are required. `PODMAN_COMMAND='sudo podman'` can select a rootful installation.

```sh
make check
make prepare
make smoke

export OBS_CREDENTIALS_FILE=/path/outside/repository/obs-credentials.json
make bootstrap
make publish
python3 scripts/verify_all.py --timeout 1800
```

For one image:

```sh
python3 scripts/prepare.py prometheus
python3 scripts/smoke.py prometheus
python3 scripts/obs.py publish prometheus
make status
make log IMAGE=prometheus
```

Preparation pulls the pinned digest, builds without network access, and exports a container that is never started. It preserves ownership, allowed extended attributes and runtime configuration, and rejects privilege-granting files. Static monitoring binaries are checked for an ELF interpreter before acceptance. The generated OBS recipe is rebuilt locally and its runtime configuration compared before upload. Signed-image verification also checks the expected unprivileged UID/GID and scans the published layers for setuid/setgid files and file capabilities.

Only allowlisted inputs enter the context. Generated archives stay under ignored `.build/obs/`; they never enter Git. The publisher checks input/archive hashes, stages source blobs, commits one complete OBS revision per package, and verifies uploaded bytes with SHA-256. It refuses unexpected remote files and detected concurrent edits. Use a single publisher; do not edit these OBS packages concurrently in the web UI.

The image contains `/usr/share/obs-container/provenance.json` with upstream digest, input hashes, runtime metadata and rootfs archive hash. Changes to applications, bundled libraries or certificates require a reviewed upstream digest and a rebuild. These images retain upstream release cadence and dependencies; scratch alone does not remediate vulnerable code inside a binary.

## Verify and deploy

```sh
python3 scripts/obs.py verify prometheus --tag 3.15.0 \
  --destination .build/verified-prometheus
```

Verification performs a Skopeo copy using a default-reject policy, the pinned public key in `keys/`, a matching image identity, and the HTTPS OBS signature store. Missing or incorrect signatures fail. OBS uses **OpenPGP simple signing**, not Cosign keyless signing. [OBS signing documentation](https://openbuildservice.org/help/manuals/obs-user-guide/cha-obs-build-containers.html)

Run the already verified bytes, for example:

```sh
skopeo copy --remove-signatures dir:.build/verified-prometheus \
  docker-archive:.build/prometheus.tar:localhost/obs-prometheus:verified
podman load -i .build/prometheus.tar
podman run --rm --pull=never --read-only --cap-drop=ALL \
  --security-opt=no-new-privileges --tmpfs /prometheus:rw,mode=1777 \
  -p 127.0.0.1:9090:9090 localhost/obs-prometheus:verified
```

This example uses ephemeral data; use persistent storage and reviewed configuration for deployment. Docker archives cannot retain detached signatures; convert only after successful verification. Plain `podman pull` does not inherit this temporary trust policy. Deploy verified content by digest or load the verified archive, and configure trust enforcement in the deployment runtime.

Runtime configuration remains application-specific:

- **Kanidm:** provide TLS, server configuration and `/data` writable by `65532:65532`. Upstream requires an x86-64-v2 capable CPU. [Deployment guide](https://kanidm.github.io/kanidm/stable/preparing_for_your_deployment.html)
- **RADIUS:** supply Kanidm connection credentials, RADIUS clients, certificates and directories writable by `497:496` as required by its upstream entrypoint. UDP 1812/1813 are exposed. The integration daemon and FreeRADIUS are tested; no live identity service is deployed here.
- **Stalwart:** persist `/etc/stalwart` and `/var/lib/stalwart`, both owned by `2000:2000`. Bootstrap uses port 8080. Configure mail/TLS listeners on internal ports above 1023 and map public ports to them (for example, host 25 to configured internal 2525). Alternatively, a deployment runtime can allow unprivileged low ports with the container network namespace's `net.ipv4.ip_unprivileged_port_start` setting. This image needs no `NET_BIND_SERVICE` capability. Configure domain, TLS and mail separately. [Docker guide](https://stalw.art/docs/install/platform/docker/)
- **Monitoring:** persist Prometheus/Alertmanager data as UID/GID 65532. Blackbox ICMP probes need suitable capabilities/kernel settings. Node exporter needs explicit host mounts/namespaces for host metrics. PostgreSQL exporter needs a database connection secret at deployment.
- **PostgreSQL:** use a password secret and persistent storage at `/var/lib/postgresql` for PostgreSQL 18. Initialization and the server both run as `70:70`; the entrypoint cannot repair root-owned bind mounts. Provision existing/bind-mounted data with that ownership before starting. New named volumes inherit the image's ownership. With a read-only root filesystem, provide writable `/var/run/postgresql` and `/tmp` too. A new image does not migrate existing databases across major versions. [Official image documentation](https://github.com/docker-library/docs/tree/master/postgres)

Run with `--cap-drop=ALL --security-opt=no-new-privileges` and the required writable volumes; the smoke tests use these restrictions for every image without a user override. They check binary execution, monitoring startup/configuration, Stalwart bootstrap readiness, and PostgreSQL initialization plus a SQL query over TCP. Running service processes are checked for root identities and capabilities. These tests do not replace deployment integration tests for identity, RADIUS, mail delivery, host metrics or database upgrades. An image's default user cannot prevent a deployment administrator from overriding it or granting privileges.

Key rotation is explicit: verification never automatically trusts a replacement key. Review the pinned fingerprint through OBS or another trusted channel. If OBS creates a key with a future timestamp, wait for clock skew and rebuild any image signed too early; do not weaken verification.

See [the validation record](docs/validation.md) and [OBS Dockerfile rules](https://openbuildservice.org/help/manuals/obs-user-guide/cha-obs-supported-formats.html).

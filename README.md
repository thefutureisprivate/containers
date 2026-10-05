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

The table records the latest validation; **the Containerfiles are the current version source of truth**. OBS publishes `NAME:VERSION-<RELEASE>`, `NAME:VERSION`, and `NAME:latest`. A pinned upstream digest is an integrity pin, not a verified upstream publisher signature. OBS signs the result under this project's identity.

See [Alpine versus scratch](docs/base-images.md) for the security tradeoffs.

Stalwart includes a pinned Web UI bundle. See [enabling the bundled UI](docs/stalwart-webui.md)
for the command and the first-time setup limitation.

Every image declares a numeric, nonzero runtime UID and GID. OBS rejects root/implicit users, setuid/setgid files, file capabilities and image labels requesting capabilities. RADIUS privilege helpers are stripped, and Stalwart's `NET_BIND_SERVICE` file capability is removed. Merged Dependabot changes must pass the same OBS build checks before publication. Build-time `USER 0:0` instructions only modify image files; the final runtime user is unprivileged.

## Dependabot and OBS builds

[Dependabot](.github/dependabot.yml) checks upstream image tags and digests daily and proposes PRs. Updates require review and merging; they are not automatically merged. Kanidm and RADIUS updates are grouped when available together. PostgreSQL major releases require a database migration plan.

GitHub stores the recipes and update PRs. **There are no GitHub Actions build, test, signing or publishing jobs, and GitHub needs no OBS account password.** Package-scoped OBS SCM webhooks notify OBS after Git changes. OBS fetches the `main` branch itself through its [SCM bridge](https://openbuildservice.org/help/manuals/obs-user-guide/cha-obs-scm-bridge.html).

OBS performs the complete image pipeline:

1. Fetch each package's Git directory and import the nine versioned upstream images using OBS's `Docker:Registry` service.
2. Build the policy helper RPM in the `tooling` repository. Each container depends on this helper.
3. Inside the isolated OBS build VM, check the imported registry digest, image configuration hash and every layer against the pin. A mismatch fails the build.
4. Build the complete Containerfile with Podman, applying file hardening and the numeric non-root user. The build uses the imported image with `--pull=never`.
5. Audit the effective filesystem for setuid/setgid files and file capabilities, validate static monitoring executables, and run the application smoke tests. A failed check prevents publication.
6. Sign successful images with the existing OBS project key and publish them to `registry.opensuse.org`.

Each package has two small recipe inputs because OBS's registry importer currently cannot resolve `FROM image:tag@sha256:digest` directly:

- **`Containerfile`** is the full runtime recipe with the immutable upstream digest.
- **`Dockerfile`** declares the same version tag for OBS's dependency scheduler. Dependabot recognizes and updates both filenames. The OBS service rejects mismatched tags, checks the imported content against the Containerfile digest, then renders the actual build recipe inside OBS.

The `#!DisableOBSContainerSupport` marker prevents OBS from injecting RPM package-manager helpers into Alpine and upstream runtimes. The custom service and post-build hook live in [`containers/obs-service-container_policy`](containers/obs-service-container_policy). Its RPM is an internal build dependency; only application images are published.

A small `obs-container-policy-revision` RPM records hashes of the shared build
checks. OBS tracks it as a rebuild dependency, so changing those checks rebuilds
every container; ordinary build-support RPMs alone would not trigger that rebuild.

The image contains `/usr/share/obs-container/provenance.json` with its recipe Git commit, canonical input hashes, build-policy hashes, upstream digest, upstream configuration hash and runtime UID/GID. These are assembly builds using pinned upstream binaries; the application binaries themselves are not recompiled from source here.

## Project administration

Local requirements: Python 3.11+, Make, GnuPG and Skopeo. Podman is also needed for the optional signed-filesystem verification. These commands configure or inspect OBS; they do not build or upload image files:

```sh
make check
export OBS_CREDENTIALS_FILE=/path/outside/repository/obs-credentials.json
make configure
make refresh
make status
make log IMAGE=prometheus
python3 scripts/verify_all.py --timeout 1800
```

`make configure` applies [`obs/project.xml`](obs/project.xml), preserving the pinned signing identity. The command also applies the root [`_config`](_config) and connects each OBS package to its Git subdirectory. Repeat configuration only when project topology or `_config` changes. `make refresh` asks OBS to fetch Git now; normal recipe updates use the package webhooks. The credential file stays outside Git and may contain JSON `username`/`password` fields or separate username/password lines, with an optional leading label.

See [webhook setup](docs/webhook.md) for the installed connection that triggers builds after a merge. The old `OBS_CREDENTIALS` Actions secret is obsolete and can be removed. Dependabot opens PRs independently of that webhook.

The signing verifier rejects unsigned images, wrong identities and unreviewed key changes. `verify_all.py` additionally checks that published provenance matches the checkout, its expected runtime UID/GID, and the merged runtime filesystem. Checking the effective filesystem matters for layered images: files removed by hardening may still exist in lower layers but cannot be executed from the resulting container filesystem.

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

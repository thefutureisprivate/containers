# Signed OBS containers

Recipes for [home:thefutureisprivate:containers](https://build.opensuse.org/project/show/home:thefutureisprivate:containers), maintained in [thefutureisprivate/containers](https://github.com/thefutureisprivate/containers). **OBS builds, tests, signs and publishes the images.** GitHub stores recipes and Dependabot PRs; there are no GitHub Actions jobs.

The runtime policy is **scratch for static Go services, Alpine for everything else**. All 20 recipes have passed builds and smoke checks in the unpublished `home:thefutureisprivate:containers:staging` project. Production publication and signature verification are in progress; see the [validation records](docs/validation.md).

## Images

All recipes target `linux/amd64`. Published image names use:

```text
registry.opensuse.org/home/thefutureisprivate/containers/containers/NAME:TAG
```

| Image | Runtime and application input | Default UID:GID |
| --- | --- | --- |
| `kanidm` | Alpine; Kanidm compiled from pinned sources in OBS | `65532:65532` |
| `kanidm-radius` | Alpine FreeRADIUS; native Kanidm module and launcher compiled in OBS | `497:496` |
| `stalwart` | Official Alpine image; bundled Web UI | `2000:2000` |
| `prometheus` | Scratch; upstream static Go binaries | `65532:65532` |
| `blackbox-exporter` | Scratch; upstream static Go binary | `65532:65532` |
| `postgres-exporter` | Scratch; upstream static Go binary | `65532:65532` |
| `node-exporter` | Scratch; upstream static Go binary | `65532:65532` |
| `alertmanager` | Scratch; upstream static Go binaries | `65532:65532` |
| `postgresql` | Official Alpine image | `70:70` |
| `certspotter` | Scratch; pinned Go module compiled in OBS | `65532:65532` |
| `certbot` | Official Alpine image | `65532:65532` |
| `nginx` | Official Alpine image, listening on 8080 | `101:101` |
| `element-web` | Official Alpine/nginx image, listening on 8080 | `101:101` |
| `synapse` | Alpine Python; pinned official musl wheels and native extensions built in OBS | `991:991` |
| `matrix-authentication-service` | Alpine; Rust binary compiled in OBS, matching official UI/policy assets | `65532:65532` |
| `home-assistant` | Official Alpine image; Core runs directly without root initialization | `65532:65532` |
| `openthread-border-router` | Alpine; OpenThread border-router sources compiled in OBS | `65532:65532` |
| `eclipse-mosquitto` | Official Alpine image, kept on major version 2 | `1883:1883` |
| `matterjs-server` | Alpine; maintained `matter-server` npm package and native modules built in OBS | `65532:65532` |
| `vaultwarden` | Official Alpine image | `65532:65532` |

The recipes and lockfiles specify current versions. OBS publishes version/release tags, version tags and `latest`. Image digests and source checksums provide integrity pins; they are not independent upstream publisher signatures. OBS signs the resulting artifacts under this project's identity.

Python Matter Server was replaced with its maintained Matter.js successor at the user's request. It is not published under the old image name. See the [upstream migration guidance](https://github.com/matter-js/python-matter-server).

## Hardening and allocator

Every final image has an explicit, numeric, nonzero UID and GID. OBS rejects setuid/setgid files, file capabilities and labels requesting capabilities. Tests use the image's default user, dropped capabilities, no-new-privileges, a read-only root filesystem and disposable writable volumes. Build-time root instructions install files; the runtime does not start as root to fix ownership.

The `hardened-malloc` OBS package compiles **one shared musl `hardened_malloc` library**. Every Alpine recipe copies those same bytes and enables `LD_PRELOAD`; image builds never compile another copy. OBS checks the source hashes, shared artifact hashes and allocator loading. Published-image verification compares the allocator's build recipe with this Git checkout too.

Allocator coverage has specific limits:

- The six static Go services have no dynamic loader, and Go's heap cannot use `LD_PRELOAD`.
- Stalwart's upstream Rust server embeds jemalloc. The preload covers its native libc allocations and dynamic helpers, not that Rust heap.
- Vaultwarden's official Alpine server is statically linked. Its server cannot preload the allocator; dynamic helper programs can.
- Python uses `PYTHONMALLOC=malloc` to route its ordinary allocations through the shared allocator. Native extensions and JavaScript engines may also have internal allocators.
- The allocator uses its default hardening configuration with native CPU tuning disabled. Its C++ allocator replacement is disabled to avoid adding a libstdc++ dependency everywhere; ordinary C++ malloc-backed allocations remain covered, but sized-delete checks are unavailable.

GrapheneOS recommends a host `vm.max_map_count` of at least `1048576` for its default allocator configuration. Configure this on deployment hosts; the images do not change host sysctls. See [hardened_malloc documentation](https://github.com/GrapheneOS/hardened_malloc) and [base-image choices](docs/base-images.md).

## Updates and builds

[Dependabot](.github/dependabot.yml) checks daily and opens reviewed PRs. It updates image pins, Cert Spotter's Go modules, Matter's npm lockfile and Synapse's pinned application version. No PR is automatically merged. PostgreSQL major upgrades still require a database migration plan.

Kanidm, RADIUS, MAS and OpenThread use `upstream/Dockerfile` as a Dependabot release watch. **These four source rebuilds need one additional step in their update PR:**

```sh
python3 scripts/update_sources.py kanidm kanidm-radius
# Or matrix-authentication-service / openthread-border-router
make check
```

The command downloads source inputs, validates versions and updates source SHA256 pins, including the Rust lockfile's crate checksums. Commit the changes to the same PR before merging. It never compiles an application. OBS rejects a changed release watch with stale source pins. Synapse source updates use `python3 scripts/update_sources.py synapse` to refresh its hash-locked musl wheels and the small extension built from source. Run it after a Synapse, Alpine-base or Python-dependency PR changes. This source-resolution command needs Podman; compilation remains in OBS. OIDC, Redis, URL previews and PostgreSQL support are included.

After a merge, package-scoped [GitHub push hooks](docs/webhook.md) ask OBS to fetch `main`. OBS then:

1. Fetches the package's Git directory, checksum-pinned source assets and native registry/APK inputs.
2. Builds the shared allocator and policy helper in its `tooling` repository.
3. Verifies each imported image's registry digest, configuration and layers, and every declared source checksum.
4. Compiles source-based applications and assembles the final Containerfile offline with Podman and `--pull=never`.
5. Audits the effective filesystem, Alpine identity or static ELF binaries, default user and allocator; then runs service smoke tests.
6. Signs successful images with the OBS project key and publishes them to `registry.opensuse.org`.

`Containerfile` is the complete, digest-pinned runtime recipe. `Dockerfile` is a declaration for OBS's scheduler, which cannot directly import digest-qualified `FROM` references. The build-time policy validates the tag/digest pair and renders the actual recipe inside OBS. Source builds declare Alpine `main` and `community` dependencies separately from the RPMs used by the OBS build VM. Rust dependencies come from the upstream `Cargo.lock` through OBS's source-asset fetcher; compilation cannot access the network.

Dependabot tracks base-image and application releases. Native Alpine packages come from OBS's `Alpine:Latest` repositories; updates to those packages can trigger OBS rebuilds independently of a Dependabot PR. OBS records their exact build inputs in each build's `_buildenv` and dependency metadata.

`/usr/share/obs-container/provenance.json` records the Git revision, input and policy hashes, source assets, upstream image/configuration and allocator build. Small dependency RPMs make policy/allocator changes trigger container rebuilds. GitHub allows only 20 push hooks per event, so the 20 applications have hooks; after changing either shared tooling package, run `make refresh` explicitly.

## Administration and verification

Local tools: Python 3.11+, Make, GnuPG and Skopeo; Podman for signed-filesystem verification. These commands configure or inspect OBS, without building or uploading image files:

```sh
make check
export OBS_CREDENTIALS_FILE=/path/outside/repository/obs-credentials.json
make configure
make refresh
make status
python3 scripts/verify_all.py --timeout 1800
python3 scripts/obs.py verify prometheus --tag latest --destination .build/verified-prometheus
```

Credentials stay outside Git. `make configure` applies the project configuration and Git package bindings while preserving the pinned signing key. `make refresh` requests Git refreshes for the two tooling packages and all applications.

Verification uses a default-reject Skopeo policy, the pinned key in `keys/`, matching image identity and the HTTPS OBS signature store. OBS uses **OpenPGP simple signing**. Missing signatures, wrong identities or unreviewed key changes fail verification. The all-image verifier also compares signed provenance against the checkout and inspects the merged filesystem. Plain `podman pull` does not inherit this temporary trust policy; deploy verified bytes or configure equivalent signature enforcement in the runtime.

## Deployment

Provision bind mounts with the image's UID:GID before startup. Use unprivileged internal ports and map public ports to them. Supply application configuration and secrets at deployment, and use `--cap-drop=ALL --security-opt=no-new-privileges` where the workload permits it. Image defaults cannot prevent an administrator from overriding the user or granting privileges.

- **Kanidm/RADIUS:** provide Kanidm TLS/configuration and `/data`; RADIUS also needs writable configuration/certificate directories and access to its identity service. RADIUS uses UDP 1812/1813.
- **Stalwart:** persist `/etc/stalwart` and `/var/lib/stalwart` as `2000:2000`. Configure unprivileged mail listeners. The [bundled UI enable command](docs/stalwart-webui.md) works on configured servers; upstream first-time setup still attempts a GitHub download.
- **PostgreSQL:** persist `/var/lib/postgresql` for PostgreSQL 18 as `70:70`, supply the password as a secret, and provide writable `/var/run/postgresql` and `/tmp` with a read-only root filesystem. Image updates do not migrate databases across major versions.
- **Monitoring/Cert Spotter:** persist required state as `65532:65532`. Cert Spotter reads `/data/watchlist`. Host metrics, ICMP probes and database export need their own mounts, permissions or connection settings.
- **Certbot:** persist `/etc/letsencrypt`, `/var/lib/letsencrypt` and `/var/log/letsencrypt` as `65532:65532`. Configure ACME credentials and the challenge method separately.
- **nginx/Element:** serve HTTP on 8080; provide writable `/tmp` for nginx. Mount Element's configuration at `/app/config.json`. TLS termination and public URL configuration are deployment choices.
- **Synapse/MAS:** provision Synapse `/data` as `991:991`; `generate` accepts `SYNAPSE_SERVER_NAME` and optional `SYNAPSE_REPORT_STATS`. Supply MAS configuration, database and identity-provider settings separately.
- **Home Assistant:** persist `/config` as `65532:65532`. This runs Core directly, without upstream root/s6 initialization or separately supervised go2rtc. Device access and Bluetooth require deployment-specific permissions.
- **OpenThread:** set `OT_INFRA_IF`, `OT_RCP_DEVICE` and optionally `OT_THREAD_IF`; persist `/var/lib/thread`. The Alpine build includes the REST API, but no web frontend or root firewall initialization. Radio devices and host/network administration permissions must be arranged by the deployment; a privileged container is not the default.
- **Mosquitto:** mount configuration and persist `/mosquitto/data` and `/mosquitto/log` as `1883:1883`. Configure authentication and TLS; the test's anonymous loopback listener is not shipped as production configuration.
- **Matter:** persist `/data` as `65532:65532`; the API uses port 5580. Follow upstream guidance for IPv6/mDNS, host networking, Bluetooth and migration from Python Matter Server. No file capabilities are added for ICMP or Bluetooth.
- **Vaultwarden:** persist `/data` as `65532:65532`; HTTP listens on 8080. Supply external URL, TLS termination and operational secrets separately.

Smoke tests cover offline startup and selected protocols. They do not replace deployment tests for real authentication, RADIUS, mail, ACME issuance, hardware radios, Bluetooth, IPv6 discovery or database upgrades.

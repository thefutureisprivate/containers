# Application image validation

## Unprivileged runtimes — 2026-10-05

Stalwart now uses the official `v0.16.24-alpine` image, pinned by digest. All nine images have explicit nonzero numeric users/groups: `65532:65532` for Kanidm and the five monitoring images, `497:496` for RADIUS, `2000:2000` for Stalwart and `70:70` for PostgreSQL. The prepared filesystems contain no setuid/setgid files or file capabilities.

All 24 unit tests and all nine local smoke tests passed. Every smoke test used the image's default user, a read-only root filesystem, `--cap-drop=ALL` and `--security-opt=no-new-privileges`. Stalwart initialized fresh configuration/data volumes and its HTTP readiness endpoint responded on port 8080. PostgreSQL initialized fresh data as UID 70 and answered `SELECT 42` over TCP after initialization. Its smoke test checks named-volume-style copy-up permissions separately and uses tmpfs for database initialization to avoid CI host disk writeback delays. Monitoring services started and their configuration checks passed. Running service processes had non-root identities and empty bounding, effective and permitted capability sets. Kanidm and RADIUS binary checks do not include live identity/RADIUS integration.

Stalwart deployment must use unprivileged internal listener ports, or a container network namespace configured to permit low ports without capabilities. PostgreSQL bind-mounted data must already be owned by `70:70`; its entrypoint no longer starts as root to change ownership.

OBS built the three changed packages from source revision 2. All nine published images passed signature verification, matching-provenance checks, runtime UID/GID checks and a scan of their signed layers for setuid/setgid files and file capabilities. The six unchanged image digests are recorded below; the changed releases are:

| Image release | Verified manifest digest |
| --- | --- |
| `kanidm-radius:1.11.2-2.1` | `sha256:f8e177d942e7e2121b9b1346649430b61a76582c7c382ec48860b82166b42668` |
| `stalwart:0.16.24-alpine-2.1` | `sha256:61c89e4f031a54558152512e1abcc150b4281327a02225003d1a3fab13fead01` |
| `postgresql:18.6-alpine3.24-2.1` | `sha256:596d878fd63a562a6c2de1cb791831d8577b9c99b5a4f7c57b9658e39caf824c` |

## Initial publication — 2026-10-03

All nine application source packages were committed to OBS as revision 1 and built successfully. The following release tags passed Skopeo signature verification with the pinned project key, and their embedded provenance matched the locally prepared inputs.

| Image release | Verified manifest digest |
| --- | --- |
| `kanidm:1.11.2-1.1` | `sha256:e1a1e5fb7df233d351a417faf2dbe371d5710fa7de0762fec67ac2955b8d16bb` |
| `kanidm-radius:1.11.2-1.1` | `sha256:97ccfe48005b853e33f89c2099ac365f8f995477b983b971297cd43275c948ce` |
| `stalwart:0.16.24-1.1` | `sha256:52682054c41e7d2376da869c621e7fac020f9b8a9856944495ac61aa360fb573` |
| `prometheus:3.15.0-1.1` | `sha256:8facf99aa13fb1770c7aa88b006a529d33a385055af3b33d42fde7bdde16bd3d` |
| `blackbox-exporter:0.28.0-1.1` | `sha256:04c99e875cb233850cbb3c4381012bce2004b62fa40d68b19e3b319ee4b7f956` |
| `postgres-exporter:0.20.1-1.1` | `sha256:922618fdac9be6326c0da1f7019811eb97778ca426b872c68b28100803552b06` |
| `node-exporter:1.12.1-1.1` | `sha256:03997d62cffc23270e914c7b34c0e0f03fa1dc1b3031157fc815cdfd2565f909` |
| `alertmanager:0.34.1-1.1` | `sha256:03945490337a2443df7212259e5cbdcc845958dbcf4bbfd858f3d9e94ef78a08` |
| `postgresql:18.6-alpine3.24-1.1` | `sha256:1281829a69be4eb6495dac65c9d725d3895f6fe69d212d5158763cfb18b1d419` |

The pinned OBS project key fingerprint is `DD87A6E5C1750F5565E2BFF04B95B6E079AF43C2`.

The full registry prefix is `registry.opensuse.org/home/thefutureisprivate/containers/containers/`.

Local checks passed: immutable input validation, static ELF checks for the five monitoring runtimes, binary execution for all nine images, monitoring service startup, Prometheus/Alertmanager configuration validation, and PostgreSQL initialization plus `SELECT 42`. Kanidm RADIUS tests cover both FreeRADIUS and the native `kanidm_radiusd` wrapper. Identity authentication, RADIUS clients, real email delivery and database migration tests need deployment configuration and are outside this initial image validation.

GitHub's Docker and GitHub Actions Dependabot scans both completed successfully after the first push. The current inputs were already up to date, so that scan did not open an update PR. Future upstream tag/digest changes are checked daily. Automated OBS publication requires the `OBS_CREDENTIALS` repository Actions secret; initial publication here used the supplied local credential file.

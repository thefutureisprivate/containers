# Application image validation

## Expanded Alpine catalog — 2026-10-05

All **20 application images** were built, tested, signed and published by
`home:thefutureisprivate:containers` from GitHub `main`. The same recipes first
passed the unpublished staging project. Production source hashes and each
package's Git revision were compared with the tested checkout before release.
The staging project now has builds and publication disabled, preserving its
successful build history.

The catalog contains **six scratch runtimes for static Go services and 14 Alpine
runtimes**. Kanidm, RADIUS, MAS and OpenThread are compiled for Alpine in OBS;
Synapse uses pinned musl wheels and an extension compiled in OBS; Matter uses
the maintained `matterjs-server` successor, with its native npm modules rebuilt
in OBS. Stalwart retains its bundled Web UI and enable command.

All **26 local policy tests** and all **20 OBS smoke checks** passed. Each final
image has an explicit nonzero numeric UID:GID, and its effective filesystem was
checked for setuid/setgid files and file capabilities. OBS checked Alpine/musl
identity or the static ELF executables and exercised applicable services with
dropped capabilities, no-new-privileges and a read-only root filesystem.
Hardware, live identity/RADIUS authentication, mail delivery, ACME issuance and
database migrations still require deployment-specific testing.

OBS built one musl allocator RPM, `obs-hardened-malloc-2026100200-1.1`, and the
policy helper `1.0-4.1`. All **14 signed Alpine images contain identical shared
allocator bytes** with SHA-256:

```text
dc9754a00ee218a6a7364b2ec50cec6c36c7f00e252e0ede309dc2e68c46bbd2
```

The verifier checked both the artifact hashes and their source/build recipe
provenance against Git, reproducing OBS's VCS and release-number additions to
the RPM spec before comparing its complete hash. Static Go, Stalwart's embedded
jemalloc, Vaultwarden's static server and other internal allocators retain the documented coverage
limits in [the README](../README.md#hardening-and-allocator).

GitHub successfully processed the expanded Dependabot configuration at commit
`f3419d81988f29c5c25efe47f49cdcb20041433f`:
[Docker](https://github.com/thefutureisprivate/containers/actions/runs/37307296155),
[Go](https://github.com/thefutureisprivate/containers/actions/runs/37307296680),
[npm](https://github.com/thefutureisprivate/containers/actions/runs/37307296554), and
[pip](https://github.com/thefutureisprivate/containers/actions/runs/37307295946).
These managed update jobs maintain dependency PRs; image compilation and assembly
remain in OBS. All 20 package-scoped GitHub hooks accepted the subsequent push
with HTTP 200. Ten Dependabot PRs were open after these scans; sampled Docker
PRs updated both `Containerfile` and the scheduler's `Dockerfile`. Those updates
remain separate from this tested release and require review before merging.

After publication, `scripts/verify_all.py` verified every release below using
the pinned OBS signing key and matching image identity. It then compared signed
Git provenance, input hashes and policy hashes, checked runtime users, and
audited each merged filesystem. The additional release check compared the
allocator across all 14 Alpine images. No application image was built locally
or in GitHub during this validation.

| Signed image release | Verified manifest digest |
| --- | --- |
| `alertmanager:0.34.1-2.3` | `sha256:4351c60950df210f3fca534c8e94ece5f707032194b42dc07319bb50e1a069fd` |
| `blackbox-exporter:0.28.0-2.3` | `sha256:de9d661d9d3e0a0833d3b58d52edfedaf3c702ff6270139f356027f942dfdc0d` |
| `certbot:5.8.0-1.1` | `sha256:a5c4f6bac0fc911a2b2bcc77e24dad2c0deb6a80b2f86e14fca35f6348b7a8e4` |
| `certspotter:0.25.0-3.1` | `sha256:8d129c957ad70bf5a900376dad8670f9515612460f6bd3dc7691443159a34cad` |
| `eclipse-mosquitto:2.1.2-alpine-1.1` | `sha256:76d1ca46abf5c5e0d777618a980ef62f8c381e0113826830a0e54e76e44f3d52` |
| `element-web:1.12.30-1.1` | `sha256:7dacd0b74db34565d57aaf474c9a511fca0a1a5d8554cfeaebf6d69babdf07f5` |
| `home-assistant:2026.9.4-1.1` | `sha256:7506307818a09dd06941b54fe327ec688c7e1a5f59d146b724fd28af16e044a7` |
| `kanidm:1.11.2-3.1` | `sha256:030c750434e3b05a6b0d8d555f4b4fd0ce37465e8bc2ae2da7429db3037dcf6e` |
| `kanidm-radius:1.11.2-4.1` | `sha256:860eadff53f855ac8b8c7d3b42e0de821eef7e3d6726d6154f4fa4504860f524` |
| `matrix-authentication-service:1.26.0-1.1` | `sha256:aed9e4a621a1a27fa3c67e44dda8977805f37690a377c3fb1040f981e2b79224` |
| `matterjs-server:1.4.0-2.1` | `sha256:8f6b8c7cac01f823ad760748b4eb82af515a6a08a5c023815eb622121941a657` |
| `nginx:1.30.0-alpine-1.1` | `sha256:c09c27d940c6d85978da309d08dbac1559cf02bea11ddcd1c1771ad3d36e0c09` |
| `node-exporter:1.12.1-2.3` | `sha256:d0f630b83367c282a384908265ffb1fa224fdaa6a9869e18a60b97f4604e34cf` |
| `openthread-border-router:2026.10.0-1.1` | `sha256:312303ce6f627c77483ef92edbce91de826211481322b1e397777de68ce2ddfe` |
| `postgres-exporter:0.20.1-2.3` | `sha256:2353880d5fb42807f5d57111c91a8596f3fdc3995f35a814487bca303725890d` |
| `postgresql:18.6-alpine3.24-4.1` | `sha256:6c16e448d9a6d136922c626edb9cd414ee7cc9ba10fd55520b8bd04bc7188719` |
| `prometheus:3.15.0-2.3` | `sha256:f8e2b9c26de289c377c1e548c8e0e11db6d56fb782d870e70e70d2f57bb4f9b2` |
| `stalwart:0.16.24-alpine-5.1` | `sha256:0847301c44517a7d0bcc9a3ab19a76114bfce8772731d667bd554e16b174a10c` |
| `synapse:1.162.0-1.1` | `sha256:0aa0e2069df8d24f4a02a61fb684de708fdd41811fbcc873691b3b99fcbd0cc1` |
| `vaultwarden:1.37.3-alpine-1.1` | `sha256:c22074b18610b503585f6a75ccf1acb26ce68f51ca7d6dcee18fc7f77397c50c` |

The registry prefix is
`registry.opensuse.org/home/thefutureisprivate/containers/containers/`.
The pinned OBS signing-key fingerprint is
`DD87A6E5C1750F5565E2BFF04B95B6E079AF43C2`.
Full local output is retained in `.build/native-verification-expanded.log`,
with machine-readable evidence in `.build/expanded-verification-results.json`
(both ignored by Git).

## Native OBS pipeline and bundled Web UI — 2026-10-05

This section records the earlier nine-image release.

All nine images were assembled, hardened, tested, signed and published by
`home:thefutureisprivate:containers`. The application binaries remain pinned
upstream inputs in this earlier release; it did not recompile the applications from source.
GitHub has no image build workflows. All ten package-scoped push webhooks returned
HTTP 200, and OBS fetched the pushed Git revisions itself.

The validated repository implementation is `8f4d2bc534c6224a29062d3728774dc3fbb434ed`.
Stalwart's recipe and enable command are from
`58be9d356e86c36ca9c6c59b8055511d3296433b`. The policy helper and its rebuild marker
were built by OBS as `1.0-3.1`. The marker is present in each container's rebuild
metadata, so changes to shared checks can trigger new container builds.

All **20 local unit tests** passed. All nine **OBS runtime checks and smoke tests**
passed. Every runtime has an explicit nonzero UID:GID; scans of each effective
filesystem found no setuid/setgid files or file capabilities. Running service
processes were checked with all capabilities dropped, no-new-privileges, a
read-only root filesystem and networking disabled. The tests exercised monitoring
startup/configuration, Stalwart fresh-volume readiness, and PostgreSQL fresh
initialization followed by `SELECT 42` over TCP. Kanidm and RADIUS checks cover
binary execution, not live identity/RADIUS integration.

Stalwart embeds official Web UI v1.0.11. OBS fetched the ZIP through the SCM
bridge, verified its pinned SHA-256 and embedded it as a read-only file. A
separate disposable configured Stalwart instance successfully ran the enable
command's API logic twice, served `/admin/` and `/account/`, and returned JavaScript
identical to the pinned ZIP with container networking disabled. The image remains
Alpine and defaults to `2000:2000`. First-time bootstrap retains its upstream
GitHub download requirement; see [the enable command and limitations](stalwart-webui.md).

After OBS reported publication, `scripts/verify_all.py` completed for all nine
releases. Skopeo enforced the pinned OBS signing key and matching image identity;
the verifier then compared Git revisions, recipe hashes, policy hashes and UI
asset provenance, checked runtime UID:GID, and audited the signed image's merged
filesystem. No application container was built locally during this verification.

| Signed image release | Verified manifest digest |
| --- | --- |
| `alertmanager:0.34.1-2.2` | `sha256:66bec9a57c9cc1cee1377b9a250bba1e874536f2128fc8f8e2c94a9e68634bdb` |
| `blackbox-exporter:0.28.0-2.2` | `sha256:6fdaaa674f2d2d96c802ab8643a8466c5d5882cdfb37668a6f49cb9b15fdec5a` |
| `kanidm:1.11.2-2.2` | `sha256:e5c7127a907709313859405d17293bb4b4e8db04cafb32bda393341955a60bf1` |
| `kanidm-radius:1.11.2-3.2` | `sha256:b3c76a50a630375490d4dcb71ed68df50cfe794296d2eead8ecd9fb6d099948a` |
| `node-exporter:1.12.1-2.2` | `sha256:a6f070ab96e4c110e9c85648c7bbbc198079285f96b709f7c20c7eafac7fa379` |
| `postgres-exporter:0.20.1-2.2` | `sha256:e2f7b2b0ba02e9d1b9b10913f7b710cc5d2acc641a0dcb16d5b76d135f0aee50` |
| `postgresql:18.6-alpine3.24-3.2` | `sha256:6cd36300de10ce0beeedbef36d8bf9eaf675e1db3d778477b98c205e0db864e7` |
| `prometheus:3.15.0-2.2` | `sha256:b8fed27bcb26cbb3ea47559a9a5de6650c18499cdaca040638ecd0046e070478` |
| `stalwart:0.16.24-alpine-4.2` | `sha256:0eb7a04d79494789d1b0c3d0481ccf9ae45f5f2e568f04349041e3d7d967a5de` |

The registry prefix is
`registry.opensuse.org/home/thefutureisprivate/containers/containers/`.
The pinned OBS signing-key fingerprint remains
`DD87A6E5C1750F5565E2BFF04B95B6E079AF43C2`.
Full local verification output is retained in `.build/native-verification.log`
(ignored by Git). The unpublished staging project also passed the native build
checks before production migration.

## Historical preparation/upload pipeline

The older records below are historical evidence for the retired pipeline.

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

GitHub's Docker and GitHub Actions Dependabot scans both completed successfully after the first push. The current inputs were already up to date, so that scan did not open an update PR. Future upstream tag/digest changes are checked daily. That earlier publication workflow used an `OBS_CREDENTIALS` Actions secret. That workflow has been removed; native OBS Git synchronization replaces it. The obsolete account secret is no longer used.

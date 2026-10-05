# Alpine or scratch?

Recommendation: use `scratch` for applications that can ship as a self-contained static executable. Use a supported Alpine release when a workload needs musl, a language runtime, or shell tooling and those requirements have been tested on Alpine. Choose per application; neither option is universally more secure.

The five Go monitoring images use scratch after static-link validation, with a CA bundle and upstream licenses. Kanidm uses its upstream scratch filesystem with required dynamic libraries. PostgreSQL and Stalwart use their official Alpine variants. RADIUS retains its upstream openSUSE runtime and native integration module.

## Why these images use different runtimes

| Images | Runtime | Reason |
| --- | --- | --- |
| Prometheus, Alertmanager, blackbox exporter, PostgreSQL exporter, node exporter | `scratch` | Their static Go executables can run with selected configuration, certificates and data directories, without a shell or package manager. |
| Kanidm | Upstream `scratch` filesystem | Upstream already assembles the server, web assets and required dynamic libraries into a minimal runtime. Scratch does not imply a statically linked executable. |
| PostgreSQL | Alpine | The official variant provides the native libraries, initialization tools and entrypoint scripts together. A scratch variant would require assembling and maintaining those dependencies ourselves. |
| Kanidm RADIUS | Upstream openSUSE | Preserve the supported FreeRADIUS installation and its native Kanidm integration module. |
| Stalwart | Official Alpine variant | Upstream supplies a musl build with certificates and runtime tooling. The image removes its file capability and runs as UID/GID 2000; bootstrap works with all capabilities dropped. |

This is a compatibility and maintenance decision per application, not a security ranking of distributions. Scratch reduces shipped components where dependencies are easy to enumerate; it also makes us responsible for supplying and updating every required file. Using one base everywhere would require additional porting and integration testing.

| Consideration | `scratch` runtime | Alpine runtime |
| --- | --- | --- |
| Shipped components | Exactly the files you add | musl, BusyBox and an APK-managed userland, plus installed packages |
| Best fit | Self-contained Go/Rust/static applications | Applications requiring a maintained Linux userland |
| Shell and package manager | Absent unless explicitly added | Usually available; remove or restrict unneeded tooling |
| Compatibility | Every runtime dependency is your responsibility | Software must work with musl; glibc assumptions need testing |
| Updates | Recompile and rebuild embedded dependencies | Rebuild from an updated base and updated packages |
| Vulnerability inventory | Must include the binary's toolchain/modules and copied assets | Package metadata helps inventory, but application dependencies still matter |

Docker documents `scratch` as an empty starting point, with the application responsible for libraries, certificates, and other required files. Omitting unused components reduces exposed functionality. An empty base is not itself a sandbox and does not remove vulnerabilities compiled into the executable. [Docker base-image documentation](https://docs.docker.com/build/building/base-images/)

Alpine supplies musl, BusyBox and a package manager, and builds its userland with PIE and stack protection. Those are useful protections, but the complete application's dependencies and update practices determine the result. Alpine's `main` and `community` repositories have different support windows; check the branch and every required package before choosing one. A small image size or a lower scanner count alone is insufficient evidence of better security. [Alpine design](https://alpinelinux.org/about/) · [Release support](https://alpinelinux.org/releases/)

## What this repository implements

- The monitoring images copy upstream executables into scratch and validate that they have no ELF interpreter. Required certificates, configuration and licenses are included.
- Every image declares a reviewed numeric, nonzero UID and GID. Monitoring images and Kanidm use `65532:65532`, RADIUS uses `497:496`, Stalwart uses `2000:2000`, and PostgreSQL uses `70:70`, including database initialization.
- Preparation rejects setuid/setgid files and file capabilities. RADIUS loses its privilege-granting helpers; Stalwart loses its low-port file capability. Smoke tests run with all capabilities dropped and `no-new-privileges`. Configure unprivileged internal listeners and storage ownership at deployment.
- A source allowlist keeps local files and credentials out of uploads. OBS signs the resulting image with its managed project key.
- The verification command requires the pinned key and a matching image identity, rejecting unsigned content.

For an HTTPS client, add and maintain a CA trust bundle. For timezone names, user lookups, dynamic libraries, subprocesses, or temporary files, supply and test the required assets explicitly. If that produces an ad hoc distribution, a maintained Alpine runtime may be easier to secure over its lifetime.

Host isolation remains necessary: use a non-root runtime, a read-only filesystem, dropped capabilities, `no-new-privileges`, resource limits, and the host's seccomp/SELinux policy. `scratch` and Alpine both share the container host kernel unless a separate sandbox provides a stronger boundary. OBS signing covers artifact provenance and integrity, not runtime isolation or vulnerability freedom.

## OBS implications

OBS workers are offline. The preparation script downloads the exact upstream image digest before submission, exports the chosen runtime, and generates a scratch-plus-rootfs recipe. For PostgreSQL, RADIUS and Stalwart this rootfs still contains the entire upstream distribution; writing `FROM scratch` in the generated recipe does not make those runtimes minimal or remove their package dependencies.

The signed provenance records the upstream digest and local input/archive hashes. Dependabot updates real Dockerfile image references through PRs, and CI rebuilds and tests the runtime before publication. OBS assembles and signs the final application images from those pinned upstream binaries. [OBS Dockerfile build rules](https://openbuildservice.org/help/manuals/obs-user-guide/cha-obs-supported-formats.html)

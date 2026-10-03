# Alpine or scratch?

Recommendation: use `scratch` for applications that can ship as a self-contained static executable. Use a supported Alpine release when a workload needs musl, a language runtime, or shell tooling and those requirements have been tested on Alpine. Choose per application; neither option is universally more secure.

This repository starts with a static Go example because no application workload has been specified. It is an application-container pipeline, separate from the ParticleOS host operating system.

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

## What the example implements

- An OBS-provided compiler builds a static Go executable with `CGO_ENABLED=0` and no external modules. Only that executable enters the final image.
- The image declares numeric UID/GID `65532:65532` and needs no writable files, network, shell, or Linux capabilities to run.
- A source allowlist keeps local files and credentials out of uploads. OBS signs the resulting image with its managed project key.
- The verification command requires the pinned key and a matching image identity, rejecting unsigned content.

For an HTTPS client, add and maintain a CA trust bundle. For timezone names, user lookups, dynamic libraries, subprocesses, or temporary files, supply and test the required assets explicitly. If that produces an ad hoc distribution, a maintained Alpine runtime may be easier to secure over its lifetime.

Host isolation remains necessary: use a non-root runtime, a read-only filesystem, dropped capabilities, `no-new-privileges`, resource limits, and the host's seccomp/SELinux policy. `scratch` and Alpine both share the container host kernel unless a separate sandbox provides a stronger boundary. OBS signing covers artifact provenance and integrity, not runtime isolation or vulnerability freedom.

## OBS implications

The builder uses openSUSE repositories because they already integrate with OBS dependency resolution. That does not make the runtime an openSUSE image. The second Dockerfile stage starts empty and copies only the application. There is no reason to introduce an Alpine runtime for this particular executable.

If a future application needs Alpine, add a distinct, tested recipe and arrange its base image and APK dependencies through OBS repositories/source services. Do not assume a Docker Hub `FROM alpine` plus online `apk add` will work in an offline OBS worker. Keep release updates and signature verification part of that recipe's lifecycle. [OBS Dockerfile build rules](https://openbuildservice.org/help/manuals/obs-user-guide/cha-obs-supported-formats.html)

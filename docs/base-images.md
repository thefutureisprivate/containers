# Alpine and scratch

This repository uses scratch for the six static Go services (Prometheus, its three exporters, Alertmanager and Cert Spotter), and Alpine for every other runtime. OBS validates static executable headers or Alpine's OS identity and musl loader before publication.

Scratch removes the shell, package manager and unrelated userland. It remains necessary to supply CA certificates, configuration and writable state explicitly. Vulnerabilities in the binary, its Go modules or toolchain remain relevant. Scratch provides no additional kernel isolation. [Docker base-image documentation](https://docs.docker.com/build/building/base-images/)

Alpine supplies musl and a maintained userland for applications needing dynamic libraries, Python, Node or shell tools. Applications without an Alpine upstream are compiled or installed for Alpine: Kanidm, its RADIUS integration, MAS, OpenThread, Synapse and Matter.js. Copying a glibc binary into Alpine is insufficient; OBS rejects a glibc loader in these final runtimes.

Neither base makes an application secure by itself. Non-root execution, prompt updates, narrow device/network permissions, dropped capabilities and deployment isolation remain necessary. Alpine's main and community repositories have different support windows; review both when advancing the base release. [Alpine design](https://alpinelinux.org/about/) · [Release support](https://alpinelinux.org/releases/)

The shared musl hardened_malloc library is compiled once in OBS and copied into every Alpine image. Static Go applications cannot preload it; Stalwart's embedded jemalloc and Vaultwarden's static server are documented coverage exceptions. See [allocator details](../README.md#hardening-and-allocator).

GitHub hosts recipes and Dependabot PRs. All compilation, assembly, runtime checks, image signing and publication take place in OBS. The signed provenance records source inputs and the shared allocator's origin; signatures establish artifact identity and integrity, not freedom from vulnerabilities.

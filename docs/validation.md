# Initial validation — 2026-10-03

The initial repository was exercised against the real [OBS project](https://build.opensuse.org/project/show/home:thefutureisprivate:containers), including download and cryptographic verification of the published container.

| Item | Observed result |
| --- | --- |
| OBS package | `hello` |
| Repository / architecture | `containers / x86_64` |
| Source revision | `2` |
| OBS source identifier | `e7ec4a0b81da96bfb8bf3251b4936391` |
| Build status | `succeeded` |
| Repository status | `published` |
| Published tags | `0.1.0-2.1`, `0.1.0`, `latest` |
| Public key | RSA 4096, SHA-256 self-signature |
| Key fingerprint | `DD87A6E5C1750F5565E2BFF04B95B6E079AF43C2` |
| Verified image manifest | `sha256:4f25eb9c5b6470d898ef26079270367bc3869a3429a0c90015cab11ebd927958` |
| Runtime user | `65532:65532` |
| Runtime filesystem | One layer, containing only `/hello` (1,507,488 bytes) |
| Executable | Statically linked x86-64 Go ELF |

The verified digest can be referenced as:

```text
registry.opensuse.org/home/thefutureisprivate/containers/containers/hello@sha256:4f25eb9c5b6470d898ef26079270367bc3869a3429a0c90015cab11ebd927958
```

Checks completed:

- Local Python tests cover credential handling, source allowlists, staged publication, concurrent source changes, SHA-256 readback, key rotation, invalid key timing, and verification failure cleanup.
- Rerunning bootstrap preserved the project and signing key.
- Skopeo accepted the registry image under a policy requiring the pinned OBS key and matching image identity.
- A real Skopeo copy accepted the locally retained signed image. Removing all signatures caused rejection. Modifying the signed manifest caused a digest-mismatch rejection.
- The downloaded layer's SHA-256 matched the manifest. Its only file was the static executable, and the OCI configuration selected the unprivileged user and `/hello` entrypoint.
- Podman ran the verified image with `--read-only`, `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--network=none`, and resource limits. It exited successfully and printed `Hello from the containers project.`

The first publication exposed clock skew between OBS key generation and image signing: its signature predated the new key's self-signature. Strict verification correctly rejected it. Revision 2 rebuilt the image after the key's creation timestamp, keeping the same key and verification policy; verification then passed. The tooling now rejects a public key that is not yet valid before publication.

This record describes the initial image. Future source or dependency updates produce new builds and must be verified again. The downloaded verification artifacts are kept locally under the ignored `.build/` directory, outside the Git sources.


## Application images — 2026-10-03

All nine application source packages were committed to OBS as revision 1 and built successfully. The following release tags passed Skopeo signature verification with the pinned project key, and their embedded provenance matched the locally prepared inputs. This validates the published application artifacts, not just the hello demonstration.

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

The full registry prefix is `registry.opensuse.org/home/thefutureisprivate/containers/containers/`.

Local checks passed: immutable input validation, static ELF checks for the five monitoring runtimes, binary execution for all nine images, monitoring service startup, Prometheus/Alertmanager configuration validation, and PostgreSQL initialization plus `SELECT 42`. Kanidm RADIUS tests cover both FreeRADIUS and the native `kanidm_radiusd` wrapper. Identity authentication, RADIUS clients, real email delivery and database migration tests need deployment configuration and are outside this initial image validation.

GitHub's Docker and GitHub Actions Dependabot scans both completed successfully after the first push. The current inputs were already up to date, so that scan did not open an update PR. Future upstream tag/digest changes are checked daily. Automated OBS publication requires the `OBS_CREDENTIALS` repository Actions secret; initial publication here used the supplied local credential file.

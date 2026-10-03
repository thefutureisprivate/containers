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

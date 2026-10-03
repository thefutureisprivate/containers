# OBS containers

Build application containers from source in [home:thefutureisprivate:containers](https://build.opensuse.org/project/show/home:thefutureisprivate:containers), sign them with the OBS project key, and publish them to `registry.opensuse.org`.

The initial `hello` image demonstrates a static Go executable in a `scratch` runtime, running as UID/GID `65532`. It prints a message and exits. It is a working example to replace with your application, not a server OS image. The openSUSE build stage supplies the compiler; the runtime contains only `/hello`.

See [the Alpine versus scratch evaluation](docs/base-images.md) for the security decision and limitations.

## Build and publish

Requirements: Python 3.10+, Make, GnuPG, an OBS account with access to this project, and Skopeo for verification. There are no Python dependencies. `osc` is optional.

```sh
make check

# Keep this file outside Git. JSON format is shown below.
export OBS_CREDENTIALS_FILE=/path/to/obs-credentials.json
make bootstrap
make publish
make status
make log
```

Credential file format (restrict it with `chmod 600`):

```json
{"username": "thefutureisprivate", "password": "YOUR_OBS_PASSWORD"}
```

Two lines containing the username and password, optionally preceded by a label, are also accepted. Credentials go only to `https://api.opensuse.org`; redirects are refused. No private signing key is downloaded or stored here.

`bootstrap` creates the project, configures its `containers/x86_64` repository, ensures a project signing key exists, and saves its **public** key and fingerprint in `keys/`. Rerunning it preserves the existing key and refuses conflicting project configuration.

`publish` uploads only the files explicitly listed in [obs/packages.json](obs/packages.json). It stages the files with SHA-256 checksums, commits one complete OBS source revision per image, and reads the committed bytes back to check their SHA-256 hashes. It refuses to delete unexpected remote sources. Use one publisher at a time; do not edit the same OBS package concurrently in the web UI.

OBS schedules builds after source changes and tracks the builder's repository dependencies. Publishing a new Git commit alone does not trigger OBS: run `make publish` after editing. A Git hosting remote and webhook are not configured by this repository.

## Verify and run

Wait for `make status` to report a successful, published build, then run:

```sh
make verify

# Optionally keep the verified image, manifest, and signatures:
python3 scripts/obs.py verify hello --tag 0.1.0 \
  --destination .build/verified-hello
```

Verification uses the pinned public key, an isolated Skopeo signature policy with a default of `reject`, and OBS's HTTPS signature store. It performs a real image copy: `skopeo inspect` by itself does not verify trust. A missing signature, wrong key, or mismatched image identity causes failure. The command prints the verified manifest digest. It currently selects `linux/amd64`, matching the configured OBS architecture.

The published image name is:

```text
registry.opensuse.org/home/thefutureisprivate/containers/containers/hello:latest
```

To run exactly the already verified bytes with Podman:

```sh
skopeo copy --remove-signatures dir:.build/verified-hello \
  docker-archive:.build/hello.tar:localhost/obs-hello:verified
podman load -i .build/hello.tar
podman run --rm --pull=never --read-only --cap-drop=ALL \
  --security-opt=no-new-privileges --network=none \
  --pids-limit=32 --memory=32m --cpus=1 localhost/obs-hello:verified
```

The temporary verification policy is not a system-wide Podman policy. A subsequent plain `podman pull` or `docker pull` does not automatically enforce it. Deploy verified content by digest and configure trust enforcement in the deployment runtime. Reusing a mutable tag after verification can retrieve different content.

The Docker archive conversion drops detached signatures because that transport cannot store them; do it only after the preceding verification succeeds. The verified directory retains the signatures.

OBS uses OpenPGP **simple signing**, not Cosign/keyless Sigstore signatures. The OBS path called `sigstore` is its signature storage location. See the [OBS signing documentation](https://openbuildservice.org/help/manuals/obs-user-guide/cha-obs-build-containers.html).

The pinned public key is bootstrapped through authenticated HTTPS to OBS. Review its fingerprint through your OBS account or another trusted channel before distributing it as a production trust root. Key rotation is explicit: verification never fetches a replacement key automatically.

If a newly created OBS key has a future creation timestamp, allow the clocks to catch up before publishing. If an image was signed before that timestamp, rebuild it afterward; waiting alone cannot repair an old signature. Never work around this by weakening the signature policy.

## Add an image

1. Add `containers/NAME/Dockerfile` and its source files. OBS package sources are flat; use a source archive for a nested application tree.
2. Set `#!BuildTag: NAME:VERSION-<RELEASE> NAME:VERSION NAME:latest`, a matching `#!BuildName`, and `#!BuildVersion` in the Dockerfile. OBS replaces `<RELEASE>` with its build release counter. Keep the published image name equal to the package name for the provided verification command.
3. Add an entry to `obs/packages.json` listing every source file to upload.
4. Run `make check`, then `make publish`.

The example compiles with `CGO_ENABLED=0` and disables Go module/toolchain downloads. OBS workers build without external network access. Vendor additional Go modules and make them available through the source package; do not introduce build-time `curl`, `git clone`, or live module downloads.

Rebuild and redeploy whenever the application, Go toolchain, or bundled assets need a security update. OBS signatures establish origin and integrity; they do not certify that an image has no vulnerabilities. Repository paths use current openSUSE Tumbleweed content, so rebuilding at a later time can use newer packages. OBS records the build inputs; this setup does not promise identical output across time.

Relevant upstream references: [Dockerfile support in OBS](https://openbuildservice.org/help/manuals/obs-user-guide/cha-obs-supported-formats.html), [OBS build configuration](https://openbuildservice.org/help/manuals/obs-user-guide/cha-obs-prjconfig.html), and [containers/image trust policy](https://github.com/containers/image/blob/main/docs/containers-policy.json.5.md).

See [the initial end-to-end validation](docs/validation.md) for the tested source revision, image digest, and runtime checks.

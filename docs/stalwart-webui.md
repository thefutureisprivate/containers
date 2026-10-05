# Bundled Stalwart Web UI

The Stalwart Alpine image includes the official Web UI **v1.0.11** at
`/usr/share/stalwart/webui.zip`, readable by the default `2000:2000` user.
OBS's SCM bridge downloads the release asset declared in the Dockerfile.
The isolated build checks SHA-256
`d67e68caba02024301c79da9f15fe465de9bf5382cee54bdf9c309a97b4179a5`
before copying it into the image; the signed provenance records the URL and hash.
No UI download or container build runs in GitHub Actions.

## Enable on a configured server

After deploying the new image, run this command from the repository checkout on
a machine with Python 3.11+ and access to Stalwart's management endpoint:

```sh
python3 containers/stalwart/enable-webui.py --url https://mail.example.org --user admin
```

The command prompts for the administrator password without echoing it. For
automation, use `--password-file /path/to/private/password-file`; do not put
passwords in command-line arguments or Git. TLS verification is always enabled.
HTTP is permitted only for localhost, for example through an SSH tunnel.

The command finds the existing built-in Web UI Application, changes its
`resourceUrl` to `file:///usr/share/stalwart/webui.zip`, enables it, reads the
settings back, and invokes Stalwart's `UpdateApps` action. That upstream action
refreshes **all enabled web applications**. Custom applications and their
settings are otherwise preserved. The command checks that `/admin/index.html`
and its JavaScript entry point are served successfully.

Stalwart serves the bundled UI at `/admin/` and `/account/` on its existing HTTP
listener. No extra web server, root process, capability or Python installation
inside the container is needed. Allow a writable `/tmp` for Stalwart's unpacked
application files when using a read-only root filesystem.

Repeat the command after an image upgrade to replace Stalwart's cached UI bundle
immediately. The local resource URL remains in Stalwart's configuration database;
the regular refresh reads that same local file rather than GitHub.

## First-time setup and updates

Stalwart 0.16.24 hardcodes the GitHub Web UI URL during initial bootstrap and
disallows editing Application objects until setup is complete. As requested,
this image keeps the upstream server binary. **Embedding the bundle does not make
first-time setup offline.** Complete upstream setup using outbound HTTPS or the
management API, then run the enable command. Existing configured installations
can enable the bundled UI without container network access to GitHub.

Dependabot updates the Stalwart container tag and digest through PRs. It does not
track arbitrary ZIP release URLs: Web UI releases require a reviewed PR changing
the matching `#!RemoteAsset` URL/hash in both recipes and the version label in
`Containerfile`. OBS rejects mismatched declarations and incorrect bundle hashes.

The OBS smoke test starts a disposable configured server with networking disabled,
read-only root, all capabilities dropped and its default non-root identity. It
uses this same enable command's API logic, repeats it to test cache refresh, and
compares the JavaScript served at both UI prefixes with the pinned ZIP contents.

Sources: [official UI release](https://github.com/stalwartlabs/webui/releases/tag/v1.0.11),
[upstream default Application](https://github.com/stalwartlabs/stalwart/blob/v0.16.24/crates/common/src/manager/defaults.rs),
[local file resource support](https://github.com/stalwartlabs/stalwart/blob/v0.16.24/crates/common/src/manager/mod.rs).

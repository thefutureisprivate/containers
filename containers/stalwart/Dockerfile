# Immutable upstream input; Dependabot updates the tag and digest in PRs.
FROM docker.io/stalwartlabs/stalwart:v0.16.24-alpine@sha256:dcff88258bf65d29ab9fc424d1006c9bda7290577151488adf2a47718d736977
# Build-time root only. Runtime needs no capabilities; use unprivileged listeners.
USER 0:0
RUN setcap -r /usr/local/bin/stalwart
USER 2000:2000

#!BuildTag: matterjs-server:latest
#!BuildName: matterjs-server
# Scheduler declarations; container_policy renders the actual Containerfile.
FROM registry-1.docker.io/library/alpine:3.24.2
RUN obs_pkg_mgr add_repo http://download.opensuse.org/repositories/Alpine:/Latest/main/
RUN obs_pkg_mgr add_repo http://download.opensuse.org/repositories/Alpine:/Latest/community/
RUN apk add nodejs npm nodejs-dev python3 build-base musl-dev linux-headers pkgconf bluez-dev eudev-dev bluez-libs eudev-libs ca-certificates iputils-ping

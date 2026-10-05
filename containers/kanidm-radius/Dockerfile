#!BuildTag: kanidm-radius:latest
#!BuildName: kanidm-radius
# Scheduler declarations; container_policy renders the actual Containerfile.
#!RemoteAsset: https://github.com/kanidm/kanidm/archive/refs/tags/v1.11.2.tar.gz sha256:a8ed31203e5f8c036b9cb261c85ddac19291bc6ca16981495495cd9621c56529 upstream.tar.gz
FROM registry-1.docker.io/library/alpine:3.24.0
RUN obs_pkg_mgr add_repo http://download.opensuse.org/repositories/Alpine:/Latest/main/
RUN obs_pkg_mgr add_repo http://download.opensuse.org/repositories/Alpine:/Latest/community/
RUN apk add cargo clang build-base cmake pkgconf openssl-dev freeradius-dev talloc-dev ca-certificates freeradius freeradius-eap freeradius-utils openssl libgcc

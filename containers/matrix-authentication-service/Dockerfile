#!BuildTag: matrix-authentication-service:latest
#!BuildName: matrix-authentication-service
# Scheduler declarations; container_policy renders the actual Containerfile.
#!RemoteAsset: https://github.com/element-hq/matrix-authentication-service/archive/refs/tags/v1.26.0.tar.gz sha256:57dbb7dabf98182819da16af364797ba6bc58b2b97ac5cf246740352d2c4fa60 upstream.tar.gz
#!RemoteAsset: https://github.com/element-hq/matrix-authentication-service/releases/download/v1.26.0/mas-cli-x86_64-linux.tar.gz sha256:351d58d47dc8fb7656d1db2d6caed73915f3923297d7ec98070de52459adced0 mas-release.tar.gz
FROM registry-1.docker.io/library/alpine:3.24.0
RUN obs_pkg_mgr add_repo http://download.opensuse.org/repositories/Alpine:/Latest/main/
RUN obs_pkg_mgr add_repo http://download.opensuse.org/repositories/Alpine:/Latest/community/
RUN apk add cargo clang build-base cmake pkgconf openssl-dev ca-certificates libgcc libstdc++

#!BuildTag: openthread-border-router:latest
#!BuildName: openthread-border-router
# Scheduler declarations; container_policy renders the actual Containerfile.
#!RemoteAsset: https://github.com/openthread/ot-br-posix/releases/download/v2026.10.0/ot-br-posix-v2026.10.0.tar.gz sha256:73345d2b5061a7c834fac0b76d4e0f741a1c5af74af749f4a216df919bf1fd3d upstream.tar.gz
FROM registry-1.docker.io/library/alpine:3.24.0
RUN obs_pkg_mgr add_repo http://download.opensuse.org/repositories/Alpine:/Latest/main/
RUN obs_pkg_mgr add_repo http://download.opensuse.org/repositories/Alpine:/Latest/community/
RUN apk add build-base musl-dev cmake ninja-build linux-headers jsoncpp-dev libmnl-dev libnftnl-dev pkgconf ca-certificates libstdc++ jsoncpp libmnl libnftnl iproute2 iptables ipset

#!BuildTag: hello:0.1.0-<RELEASE> hello:0.1.0 hello:latest
#!BuildName: hello
#!BuildVersion: 0.1.0
#!UseOBSRepositories

# OBS resolves this base and the Go RPM through the project's repository paths.
# The builder is discarded; no distribution packages enter the final image.
FROM opensuse/tumbleweed:latest AS build
RUN zypper --non-interactive install --no-recommends go && zypper clean --all
WORKDIR /src
COPY go.mod main.go ./
ENV CGO_ENABLED=0 GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off
RUN go build -trimpath -buildvcs=false -ldflags="-s -w" -o /out/hello . && /out/hello

FROM scratch
COPY --from=build /out/hello /hello
LABEL org.opencontainers.image.title="OBS scratch example" \
      org.opencontainers.image.description="Static, non-root example application built in OBS" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.vendor="thefutureisprivate" \
      org.opencontainers.image.url="https://build.opensuse.org/project/show/home:thefutureisprivate:containers" \
      org.opencontainers.image.source="https://build.opensuse.org/package/show/home:thefutureisprivate:containers/hello"
USER 65532:65532
ENTRYPOINT ["/hello"]

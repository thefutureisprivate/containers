# Immutable upstream input; Dependabot updates the tag and digest in PRs.
FROM quay.io/prometheus/prometheus:v3.15.0@sha256:efd719c99d83b060d9daefdcf00360461adf279f45ef5391f8d111892118753e AS upstream
FROM scratch
COPY LICENSE /LICENSE
COPY NOTICE /NOTICE
COPY --from=upstream /bin/prometheus /bin/prometheus
COPY --from=upstream /bin/promtool /bin/promtool
COPY --from=upstream /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=upstream /etc/prometheus/prometheus.yml /etc/prometheus/prometheus.yml
COPY --from=upstream --chown=65532:65532 /prometheus /prometheus
WORKDIR /prometheus
VOLUME ["/prometheus"]
USER 65532:65532
EXPOSE 9090
ENTRYPOINT ["/bin/prometheus"]
CMD ["--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.path=/prometheus"]

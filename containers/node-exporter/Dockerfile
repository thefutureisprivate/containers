# Immutable upstream input; Dependabot updates the tag and digest in PRs.
FROM quay.io/prometheus/node-exporter:v1.12.1@sha256:1b4e4438faca4dd7e001dd445d161a4a2091b0fededa84093b3a8dfeae1f1be0 AS upstream
FROM scratch
COPY LICENSE /LICENSE
COPY NOTICE /NOTICE
COPY --from=upstream /bin/node_exporter /bin/node_exporter
COPY --from=upstream /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
USER 65532:65532
EXPOSE 9100
ENTRYPOINT ["/bin/node_exporter"]

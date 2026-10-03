# Immutable upstream input; Dependabot updates the tag and digest in PRs.
FROM quay.io/prometheus/blackbox-exporter:v0.28.0@sha256:e753ff9f3fc458d02cca5eddab5a77e1c175eee484a8925ac7d524f04366c2fc AS upstream
FROM scratch
COPY LICENSE /LICENSE
COPY NOTICE /NOTICE
COPY --from=upstream /bin/blackbox_exporter /bin/blackbox_exporter
COPY --from=upstream /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=upstream /etc/blackbox_exporter/config.yml /etc/blackbox_exporter/config.yml
USER 65532:65532
EXPOSE 9115
ENTRYPOINT ["/bin/blackbox_exporter"]
CMD ["--config.file=/etc/blackbox_exporter/config.yml"]

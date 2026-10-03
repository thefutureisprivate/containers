# Immutable upstream input; Dependabot updates the tag and digest in PRs.
FROM quay.io/prometheuscommunity/postgres-exporter:v0.20.1@sha256:ac5ec343104fae0e2d84a27bb8d69b38430a11910c5382cad85d478d2bab713e AS upstream
FROM scratch
COPY LICENSE /LICENSE
COPY NOTICE /NOTICE
COPY --from=upstream /bin/postgres_exporter /bin/postgres_exporter
COPY --from=upstream /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
USER 65532:65532
EXPOSE 9187
ENTRYPOINT ["/bin/postgres_exporter"]

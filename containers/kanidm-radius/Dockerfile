# Immutable upstream input; Dependabot updates the tag and digest in PRs.
FROM docker.io/kanidm/radius:1.11.2@sha256:38385f714365588f160b0329eec6298b991ddec64a260ae22de88baafcc18711
# Build-time root only. User-namespace mapping helpers carry file capabilities.
USER 0:0
RUN rm /usr/bin/newuidmap /usr/bin/newgidmap \
    && find / -xdev -type f \( -perm -4000 -o -perm -2000 \) -exec chmod a-s {} +
USER 497:496
EXPOSE 1812/udp 1813/udp

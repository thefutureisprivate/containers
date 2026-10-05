#!/bin/sh
set -eu
if [ "$#" -gt 0 ]; then exec /usr/sbin/otbr-agent "$@"; fi
: "${OT_INFRA_IF:?Set OT_INFRA_IF to the deployment infrastructure interface}"
exec /usr/sbin/otbr-agent -d "${OT_LOG_LEVEL:-4}" -v -s \
    -I "${OT_THREAD_IF:-wpan0}" -B "$OT_INFRA_IF" \
    "${OT_RCP_DEVICE:-spinel+hdlc+uart:///dev/ttyACM0?uart-baudrate=1000000}" \
    "trel://$OT_INFRA_IF" --rest-listen-address "${OT_REST_LISTEN_ADDR:-0.0.0.0}" \
    --rest-listen-port "${OT_REST_LISTEN_PORT:-8081}"

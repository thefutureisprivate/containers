#!/bin/sh
set -eu
if [ "${1:-}" = generate ]; then
    : "${SYNAPSE_SERVER_NAME:?Set SYNAPSE_SERVER_NAME before generating a configuration}"
    exec python3 -m synapse.app.homeserver --server-name "$SYNAPSE_SERVER_NAME" \
        --config-path /data/homeserver.yaml --data-directory /data \
        --generate-config --report-stats "${SYNAPSE_REPORT_STATS:-no}"
fi
exec python3 -m synapse.app.homeserver --config-path /data/homeserver.yaml "$@"

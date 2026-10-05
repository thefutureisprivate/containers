# GitHub push notifications to OBS

A merged PR changes `main`; a GitHub push hook requests a package refresh, and OBS fetches `main` from Git. The notification neither uploads layers nor runs a GitHub build.

The expanded catalog needs 20 application hooks. Each uses a `runservice` token bound to its exact OBS project and package. GitHub limits repository hooks to 20 for each event, so the allocator and policy helper use explicit `make refresh` after changes. No account-wide token is used. [GitHub webhook limits](https://docs.github.com/en/webhooks/testing-and-troubleshooting-webhooks/troubleshooting-webhooks)

The original nine application hooks and helper hook were installed and verified on 2026-10-05. Expansion requires removing the old helper hook before installing the full application set; validation records will record completion.

After `make configure`, prepare a new private configuration outside Git:

```sh
export OBS_CREDENTIALS_FILE=/tmp/obs-creds
python3 scripts/setup_webhooks.py prepare /tmp/containers-obs-webhooks-v2.json
python3 scripts/setup_webhooks.py install /tmp/containers-obs-webhooks-v2.json \
  --github-token-file /path/outside/repository/github-webhook-token
```

The output file is mode 600 and contains webhook secrets. Keep it outside Git. The script reuses matching package tokens and does not print them. The GitHub token needs only repository **Webhooks: read and write**.

Alternatively, use [Settings → Webhooks](https://github.com/thefutureisprivate/containers/settings/hooks), copying each entry's URL and secret. Select JSON, push events only, and SSL verification. OBS validates GitHub's HMAC signature and fetches the configured branch even when the notification concerns another branch.

Check deliveries for HTTP 200 and inspect OBS results with `make status`. A successful hook confirms only the refresh request; successful builds and verified published signatures establish completion. `make refresh` also works if a hook is unavailable. The obsolete GitHub Actions `OBS_CREDENTIALS` secret is unused.

[OBS webhook documentation](https://openbuildservice.org/help/manuals/obs-user-guide/cha-obs-source-services.html#sec-obs-sserv-token-usage)

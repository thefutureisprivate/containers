# GitHub push notifications to OBS

Dependabot opens update PRs. Merging a PR changes `main`; GitHub sends a push notification and OBS fetches the configured `main` branch. The event does not upload image layers or execute a GitHub build.

Each of the nine application packages and the build-policy package gets its own OBS `runservice` token and GitHub webhook. Tokens are bound to the exact OBS project and package. This avoids an account-wide token and works with OBS's package Git synchronization.

After `make configure`, prepare the hooks using credentials outside this repository:

```sh
export OBS_CREDENTIALS_FILE=/tmp/obs-creds
python3 scripts/setup_webhooks.py prepare /tmp/containers-obs-webhooks.json
```

The output is a mode-600 file containing webhook secrets. Keep it outside Git. The script reuses matching existing package tokens. It never prints their strings.

Install all ten hooks with a GitHub token restricted to this repository and **Webhooks: read and write**:

```sh
python3 scripts/setup_webhooks.py install /tmp/containers-obs-webhooks.json \
  --github-token-file /path/outside/repository/github-webhook-token
```

Alternatively, add each entry in [repository Settings → Webhooks](https://github.com/thefutureisprivate/containers/settings/hooks): use its `config.url`, `application/json`, and `config.secret`; keep SSL verification enabled and select push events only. The secret authenticates the request using GitHub's HMAC signature. OBS always fetches the `main` branch specified in package metadata, including when a push notification concerns another branch.

Check recent webhook deliveries for HTTP 200 and run `make status` to inspect OBS. A webhook delivery only confirms the refresh request; build logs and published signatures determine whether the image completed successfully. While hooks are not installed, use `make refresh` after a merge.

The old GitHub Actions `OBS_CREDENTIALS` secret is no longer used and can be removed. GitHub only needs the restricted refresh tokens; OBS keeps its image signing key.

[OBS source-service webhook documentation](https://openbuildservice.org/help/manuals/obs-user-guide/cha-obs-source-services.html#sec-obs-sserv-token-usage)

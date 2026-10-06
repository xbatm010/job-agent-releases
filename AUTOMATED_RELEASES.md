# Automated Job Agent releases

This repository publishes macOS Job Agent releases with GitHub Actions.

## How it works

1. `release-request.json` describes the next release.
2. A push that changes that file triggers `.github/workflows/publish-release.yml`.
3. The workflow runs on GitHub's arm64 macOS runner.
4. It builds `Job Agent.app` with PyInstaller.
5. It signs the bundle ad-hoc, packages it with `ditto`, and computes SHA-256.
6. It creates or updates the GitHub Release.
7. It updates `manifest.json` with the exact asset URL and SHA-256.
8. It sets `publish=false` after a successful release.

## Source privacy

The public `source/` directory must not contain:
- CV documents
- personal email addresses
- personal phone numbers
- hard-coded candidate names

Candidate profile data and CV paths are stored locally by the desktop app under macOS Application Support.

## Publishing a future version

Update the sanitized files in `source/`, then change `release-request.json`:

```json
{
  "publish": true,
  "version": "2.2.0",
  "channel": "stable",
  "min_version": "2.1.0",
  "base_source_url": "",
  "base_source_sha256": "",
  "notes": "Release notes"
}
```

The workflow handles the build, release asset, checksum and manifest automatically.

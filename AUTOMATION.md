# Automated Job Agent releases

This repository uses GitHub Actions to build and publish Job Agent Desktop.

## Privacy model

The public source bundle must not contain the user's CV, name, email, phone,
gender, or other private profile data. Those values live locally in the macOS
Application Support settings.

The workflow also refuses to publish a source bundle containing PDF/DOC/DOCX
files.

## Bootstrap

One source bundle must be uploaded manually once:

`job-agent-source-2.1.0.zip`

Attach it to GitHub Release `v2.0.3`.

After that, set `publish=true` in `release-request.json`. The workflow will:

1. download the source bundle;
2. optionally apply a patch;
3. build Job Agent on a GitHub-hosted ARM64 macOS runner;
4. create the release;
5. upload both the app ZIP and the updated source ZIP;
6. calculate SHA-256;
7. update `manifest.json`;
8. commit the manifest automatically.

Future releases can use the previous release's `job-agent-source-X.Y.Z.zip`
as their base and an optional text patch in this repository.

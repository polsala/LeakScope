# GHCR

Images publish to `ghcr.io/polsala/leakscope` using the automatic GITHUB_TOKEN,
with packages:write only in release publication/finalization jobs. No PAT is
required for publication. Docker login uses stdin and a temporary Docker config;
credentials are never included in artifacts.

Every version has its own immutable-intent tag. An existing tag must have exactly
the validated image config digest; the workflow refuses a mismatched overwrite.
The manifest response digest is independently SHA256 checked and recorded.
Source, commit, SemVer, license and creation labels are included. The build runs
the installed application journey with no network and `--cap-drop ALL` before
saving the image for publication. The same validated image is pushed later.

Prereleases never set `latest`. Stable promotion rechecks all production evidence
and registry publications, serializes finalization and refuses to demote a newer
stable latest release. GitHub Packages visibility follows repository/organization
policy; a repository owner may need to make the first GHCR package public in its
settings if public anonymous pulls are desired. This is not an additional token
requirement. Actual visibility is not claimed before the first publication.

The default API is UID 10001, binds to loopback and grants no BPF capabilities.
For Linux loopback use without weakening bind policy:

```sh
docker run --rm --network host -v leakscope-data:/data \
  ghcr.io/polsala/leakscope:0.2.0-rc.1
```

Use a separately authorized sensor configuration for host ERP profiling. Host
networking does not grant host process namespace access or tracing privileges.

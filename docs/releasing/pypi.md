# PyPI

The `leakscope` wheel is the Python collector/backend/CLI component, not the full
standalone application. It includes migration resources and requires Python
3.11+. Sensor/analyzer executables and web assets are installed separately; see
the wheel's README and the standalone installation guide. Package installation
performs no executable downloads.

The build runs strict Twine metadata checks, installs the wheel offline in a clean
venv, checks the actual CLI/imports/version, and executes database migrations.
The workflow installs hash-locked Twine dependencies before exposing credentials.

The existing secret is used only in the publishing step:

```yaml
TWINE_USERNAME: __token__
TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
```

The upload endpoint is fixed to https://upload.pypi.org/legacy/. No Trusted
Publishing, OIDC or id-token permission is used by this job. First upload creates
the project if the name is available and the account/token permits creation.
No package rename or `--skip-existing` masks conflicts.

The public project repository and existing filenames/SHA256 digests are checked.
A partial upload can resume only its missing wheel/sdist; mismatched or unexpected
existing files fail for reconciliation. Finalization waits for both correct file
digests through PyPI's API. A scope, account verification or name collision error
leaves the GitHub release in draft. Rotate/fix the existing credential if needed,
then rerun failed jobs with the same validated bundle.

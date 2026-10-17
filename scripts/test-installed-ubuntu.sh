#!/usr/bin/env bash
# Actual Debian/tarball installs, no host Python and no network at runtime.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
mkdir -p artifacts/deployment
for version in 20.04 22.04 24.04; do
  docker run --rm --network none --entrypoint /bin/bash \
    -v "$PWD/artifacts:/artifacts:ro" -v "$PWD/scripts:/qa/scripts:ro" -v "$PWD/tests/support:/qa/tests/support:ro" \
    "ubuntu:$version" -ec '
      dpkg -i /artifacts/leakscope_0.1.0_amd64.deb
      bash /opt/leakscope-distribution/install.sh /opt/leakscope
      useradd --uid 10001 --create-home qa
      cd /tmp
      if /opt/leakscope/bin/leakscope serve > /tmp/root-api.log 2>&1; then
        echo "Root API startup must be refused" >&2; exit 1
      fi
      grep -q "unprivileged service UID" /tmp/root-api.log
      su -s /bin/sh qa -c "/opt/leakscope/venv/bin/python -I /qa/scripts/validate-package.py --prefix /opt/leakscope" 
      bash /opt/leakscope-distribution/install.sh /opt/leakscope
      /opt/leakscope/bin/leakscope --version
      # Debian uninstall removes the distribution, never application/data.
      dpkg -r leakscope
      /opt/leakscope/bin/leakscope --version
      tar -xzf /artifacts/leakscope-0.1.0-linux-x86_64.tar.gz -C /tmp
      bash /tmp/leakscope-0.1.0-linux-x86_64/install.sh /opt/leakscope-tar
      su -s /bin/sh qa -c "/opt/leakscope-tar/venv/bin/python -I /qa/scripts/validate-package.py --prefix /opt/leakscope-tar"
      getconf GNU_LIBC_VERSION
    ' > "artifacts/deployment/ubuntu-$version.log" 2>&1
  printf '{"ubuntu":"%s","installed_package_smoke":true,"kernel_qualified":false}\n' "$version" > "artifacts/deployment/ubuntu-$version.json"
done

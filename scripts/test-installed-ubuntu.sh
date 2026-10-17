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
      cp -a /opt/leakscope-distribution /tmp/tampered-distribution
      touch /tmp/tampered-distribution/unexpected
      if bash /tmp/tampered-distribution/verify.sh /tmp/tampered-distribution; then
        echo "Unexpected distribution content must fail integrity validation" >&2; exit 1
      fi
      rm /tmp/tampered-distribution/unexpected
      ln -s /etc/passwd /tmp/tampered-distribution/unexpected-link
      if bash /tmp/tampered-distribution/verify.sh /tmp/tampered-distribution; then
        echo "Unexpected symlinks must fail integrity validation" >&2; exit 1
      fi
      test "$(stat -c %u /opt/leakscope/current/bin/leakscope-sensor)" = 0
      useradd --uid 10001 --create-home qa
      su -s /bin/sh qa -c "test ! -w /opt/leakscope/current/bin/leakscope-sensor && test ! -w /opt/leakscope/current/bin"
      mkdir /tmp/qa-restore
      chown qa /tmp/qa-restore
      if LEAKSCOPE_DATA=/tmp/qa-restore /opt/leakscope/bin/leakscope restore /tmp/missing-backup > /tmp/restore-owner.log 2>&1; then
        echo "Restore must refuse a different data owner" >&2; exit 1
      fi
      grep -q "data-directory owner" /tmp/restore-owner.log
      cd /tmp
      if /opt/leakscope/bin/leakscope serve > /tmp/root-api.log 2>&1; then
        echo "Root API startup must be refused" >&2; exit 1
      fi
      grep -q "unprivileged service UID" /tmp/root-api.log
      if setpriv --ruid=10001 --euid=0 --regid=10001 --egid=10001 --clear-groups /opt/leakscope/bin/leakscope serve > /tmp/effective-root-api.log 2>&1; then
        echo "Effective-root API startup must be refused" >&2; exit 1
      fi
      grep -q "unprivileged service UID" /tmp/effective-root-api.log
      su -s /bin/sh qa -c "/opt/leakscope/venv/bin/python -I /qa/scripts/validate-package.py --prefix /opt/leakscope --data /tmp/leakscope-preserved"
      bash /opt/leakscope-distribution/install.sh /opt/leakscope
      /opt/leakscope/bin/leakscope --version
      # Debian uninstall removes the distribution, never application/data.
      dpkg -r leakscope
      /opt/leakscope/bin/leakscope --version
      su -s /bin/sh qa -c "/opt/leakscope/venv/bin/python -I /qa/scripts/validate-package.py --prefix /opt/leakscope --data /tmp/leakscope-preserved"
      tar -xzf /artifacts/leakscope-0.1.0-linux-x86_64.tar.gz -C /tmp
      bash /tmp/leakscope-0.1.0-linux-x86_64/install.sh /opt/leakscope-tar
      su -s /bin/sh qa -c "/opt/leakscope-tar/venv/bin/python -I /qa/scripts/validate-package.py --prefix /opt/leakscope-tar"
      getconf GNU_LIBC_VERSION
    ' > "artifacts/deployment/ubuntu-$version.log" 2>&1
  printf '{"ubuntu":"%s","installed_package_smoke":true,"kernel_qualified":false}\n' "$version" > "artifacts/deployment/ubuntu-$version.json"
done

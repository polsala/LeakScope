#!/usr/bin/env bash
# Native ABI checks are independent of host/kernel tracing permissions.
set -euo pipefail
mkdir -p artifacts/native-baseline artifacts/compatibility
docker build -f packaging/docker/Dockerfile.native --target binaries --output artifacts/native-baseline .
for version in 20.04 22.04 24.04; do
  docker run --rm --network none -v "$PWD/artifacts/native-baseline:/native:ro" "ubuntu:$version" sh -ec '
    getconf GNU_LIBC_VERSION
    ldd /native/leakscope-sensor
    ldd /native/leakscope-analyzer
    /native/leakscope-sensor --version
    printf "" | /native/leakscope-analyzer
    /native/leakscope-sensor --doctor
  ' > "artifacts/compatibility/ubuntu-$version.txt"
done

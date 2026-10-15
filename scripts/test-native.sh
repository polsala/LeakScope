#!/usr/bin/env bash
set -euo pipefail
mkdir -p artifacts
cargo test --workspace --locked
cc -O2 -std=c99 -Wall -Wextra -Werror tests/fixtures/native_allocation_fixture.c -o artifacts/native-fixture
cc -O2 -std=c99 -Wall -Wextra -Werror tests/fixtures/realloc_edge_cases.c -o artifacts/realloc-fixture
artifacts/native-fixture
artifacts/realloc-fixture
clang -target bpf -O2 -g -Wall -Werror -I bpf/include -c bpf/probes/allocations.bpf.c -o artifacts/allocations.bpf.o
if [[ "${SANITIZE:-0}" == 1 ]]; then
  cc -g -fsanitize=address,undefined tests/fixtures/native_allocation_fixture.c -o artifacts/native-sanitized
  artifacts/native-sanitized
fi

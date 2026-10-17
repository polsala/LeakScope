#!/usr/bin/env bash
# Offline, versioned installation. No network, privileged actions or data deletion.
set -euo pipefail
source_root="$(cd "$(dirname "$0")" && pwd)"
prefix="$(realpath -m "${1:-$HOME/.local/lib/leakscope}")"
(cd "$source_root" && sha256sum --check --quiet FILES.sha256)
release_id="$(cat "$source_root/source-fingerprint")"
[[ "$release_id" =~ ^[a-f0-9]{64}$ ]] || { echo 'Invalid build identity' >&2; exit 2; }
mkdir -p "$prefix/releases" "$prefix/bin"
exec 9>"$prefix/install.lock"
flock -n 9 || { echo 'Another installation is active' >&2; exit 2; }
release="$prefix/releases/$release_id"
if [[ ! -e "$release/.installed" ]]; then
  [[ ! -e "$release" ]] || { echo "Incomplete release exists: $release; preserve logs and remove it before retry" >&2; exit 2; }
  mkdir "$release"
  cp -a "$source_root/." "$release/"
  "$release/runtime/bin/python3.12" -I -m venv "$release/venv"
  "$release/venv/bin/python" -I -m pip install --no-index --find-links "$release/wheels" leakscope==0.1.0
  cp "$release/launcher" "$release/bin/leakscope"
  chmod 755 "$release/bin/leakscope"
  "$release/bin/leakscope" --version
  touch "$release/.installed"
fi
# Keep the previous application, without modifying configuration or database.
if [[ -L "$prefix/current" && "$(readlink "$prefix/current")" != "releases/$release_id" ]]; then
  ln -s "$(readlink "$prefix/current")" "$prefix/previous.new"
  mv -Tf "$prefix/previous.new" "$prefix/previous"
fi
ln -s "releases/$release_id" "$prefix/current.new"
mv -Tf "$prefix/current.new" "$prefix/current"
for executable in leakscope leakscope-sensor leakscope-analyzer; do
  ln -sfn "../current/bin/$executable" "$prefix/bin/$executable"
done
for resource in source-fingerprint venv runtime docs web-dist; do
  ln -sfn "current/$resource" "$prefix/$resource"
done
printf 'Installed offline at %s. Configuration, captures and reports are untouched.\n' "$prefix"
printf 'Run %s/bin/leakscope doctor, then %s/bin/leakscope serve\n' "$prefix" "$prefix"

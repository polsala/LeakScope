#!/usr/bin/env bash
# Application rollback only; schema rollback requires an operator-verified backup.
set -euo pipefail
prefix="$(realpath "${1:?Usage: rollback.sh INSTALL_PREFIX}")"
exec 9>"$prefix/install.lock"
flock -n 9 || exit 2
[[ -L "$prefix/previous" && -L "$prefix/current" ]] || { echo 'No previous release available' >&2; exit 2; }
previous="$(readlink "$prefix/previous")"
[[ "$previous" =~ ^releases/[a-f0-9]{64}$ ]] || exit 2
"$prefix/$previous/bin/leakscope" --version
current="$(readlink "$prefix/current")"
ln -s "$previous" "$prefix/current.new"
mv -Tf "$prefix/current.new" "$prefix/current"
ln -s "$current" "$prefix/previous.new"
mv -Tf "$prefix/previous.new" "$prefix/previous"
echo 'Application rolled back. Restore a verified database backup before restart if schema compatibility requires it.'

#!/usr/bin/env bash
# Application rollback only; schema rollback requires an operator-verified backup.
set -euo pipefail
umask 022
prefix="$(realpath "${1:?Usage: rollback.sh INSTALL_PREFIX}")"
[[ "$(stat -c %u "$prefix")" = "$(id -u)" && ! -L "$prefix/install.lock" ]] || { echo 'Rollback prefix ownership or lock is unsafe' >&2; exit 2; }
exec 9>"$prefix/install.lock"
flock -n 9 || exit 2
[[ -L "$prefix/previous" && -L "$prefix/current" ]] || { echo 'No previous release available' >&2; exit 2; }
previous="$(readlink "$prefix/previous")"
[[ "$previous" =~ ^releases/[a-f0-9]{64}$ ]] || exit 2
if [[ "$(id -u)" = 0 ]] && [[ -n "$(find "$prefix/$previous" -xdev \( ! -user root -o -perm /022 \) -print -quit)" ]]; then
  echo 'Previous release is writable by another account; audit it before privileged rollback' >&2; exit 2
fi
"$prefix/$previous/bin/leakscope" --version
current="$(readlink "$prefix/current")"
ln -s "$previous" "$prefix/current.new"
mv -Tf "$prefix/current.new" "$prefix/current"
ln -s "$current" "$prefix/previous.new"
mv -Tf "$prefix/previous.new" "$prefix/previous"
echo 'Application rolled back. Restore a verified database backup before restart if schema compatibility requires it.'

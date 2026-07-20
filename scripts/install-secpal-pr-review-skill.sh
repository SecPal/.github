#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repository_root="$(cd "$script_dir/.." && pwd -P)"
source_path="$repository_root/.agents/skills/secpal-pr-review"
target_root="${HOME:?HOME must identify the installation account}/.agents/skills"
repair=false

usage() {
  printf 'Usage: %s [--source PATH] [--target-root PATH] [--repair]\n' "$0"
}

while (($#)); do
  case "$1" in
    --source)
      (($# >= 2)) || {
        usage >&2
        exit 2
      }
      source_path=$2
      shift 2
      ;;
    --target-root)
      (($# >= 2)) || {
        usage >&2
        exit 2
      }
      target_root=$2
      shift 2
      ;;
    --repair)
      repair=true
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ -d "$source_path" && -f "$source_path/SKILL.md" ]] || {
  printf 'Skill source is missing or incomplete: %s\n' "$source_path" >&2
  exit 1
}
canonical_source="$(cd "$source_path" && pwd -P)"
[[ "$canonical_source" != / && "$canonical_source" == /* ]] || {
  printf 'Skill source did not resolve to a safe absolute directory\n' >&2
  exit 1
}

if [[ -L "$target_root" ]]; then
  printf 'Refusing a symlink as the skill target root: %s\n' "$target_root" >&2
  exit 1
fi
mkdir -p -- "$target_root"
[[ -d "$target_root" && ! -L "$target_root" ]] || {
  printf 'Skill target root is not a direct directory: %s\n' "$target_root" >&2
  exit 1
}
canonical_target_root="$(cd "$target_root" && pwd -P)"
target="$canonical_target_root/secpal-pr-review"

if [[ -L "$target" ]]; then
  existing="$(readlink "$target")"
  if [[ "$existing" == "$canonical_source" && "$(readlink -f "$target")" == "$canonical_source" ]]; then
    printf '%s -> %s\n' "$target" "$canonical_source"
    exit 0
  fi
  if [[ "$repair" != true ]]; then
    printf 'Refusing unexpected skill symlink: %s -> %s\n' "$target" "$existing" >&2
    exit 1
  fi
  rm -- "$target"
elif [[ -e "$target" ]]; then
  printf 'Refusing to overwrite non-symlink skill target: %s\n' "$target" >&2
  exit 1
fi

ln -s -- "$canonical_source" "$target"
[[ -L "$target" && "$(readlink "$target")" == "$canonical_source" && "$(readlink -f "$target")" == "$canonical_source" ]] || {
  printf 'Skill installation verification failed: %s\n' "$target" >&2
  exit 1
}
printf '%s -> %s\n' "$target" "$canonical_source"

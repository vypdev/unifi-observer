#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY_URL="${UNIFI_OBSERVER_REPOSITORY_URL:-https://github.com/vypdev/unifi-observer.git}"
REF="${UNIFI_OBSERVER_REF:-master}"

fail() {
  if declare -F ui_error >/dev/null 2>&1; then
    ui_error "$*"
  else
    printf 'unifi-observer installer: error: %s\n' "$*" >&2
  fi
  exit 1
}

usage() {
  cat <<'EOF'
Usage: install.sh

Downloads a selected UniFi Observer revision into a temporary directory,
installs the CLI into a user-owned isolated virtual environment, and starts
the interactive configuration wizard.

Environment:
  UNIFI_OBSERVER_REF                 Git branch or tag (default: master)
  UNIFI_OBSERVER_REPOSITORY_URL      Git repository URL
  UNIFI_OBSERVER_SKIP_CONFIGURE      Set to 1 only for installation tests
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

command -v git >/dev/null 2>&1 || fail "git is required"
[[ "$REF" =~ ^[A-Za-z0-9._/-]+$ ]] || fail "UNIFI_OBSERVER_REF contains unsupported characters"
[[ "$REPOSITORY_URL" == https://* ]] || fail "repository URL must use HTTPS"
[[ "$REPOSITORY_URL" != *$'\n'* && "$REPOSITORY_URL" != *$'\r'* ]] || fail "repository URL contains a newline"

checkout="$(mktemp -d "${TMPDIR:-/tmp}/unifi-observer.XXXXXX")"
cleanup() {
  rm -rf "$checkout"
}
trap cleanup EXIT

download_repository() {
  if [[ ! -t 1 ]]; then
    git clone --quiet --depth 1 --branch "$REF" "$REPOSITORY_URL" "$checkout/repository" 2>/dev/null
    return
  fi

  local frames='|/-\\' frame_index=0 clone_pid color_start='' color_end=''
  if [[ -z "${NO_COLOR:-}" ]]; then
    color_start=$'\033[36m'
    color_end=$'\033[0m'
  fi
  git clone --quiet --depth 1 --branch "$REF" "$REPOSITORY_URL" "$checkout/repository" >/dev/null 2>&1 &
  clone_pid=$!
  while kill -0 "$clone_pid" 2>/dev/null; do
    printf '\r  %s%s%s Downloading UniFi Observer %s' "$color_start" "${frames:frame_index:1}" "$color_end" "$REF"
    frame_index=$(( (frame_index + 1) % 4 ))
    sleep 0.08
  done
  if wait "$clone_pid"; then
    printf '\r\033[2K'
    return 0
  fi
  printf '\r\033[2K'
  return 1
}

download_repository || fail "could not download the selected revision"

setup="$checkout/repository/scripts/setup.sh"
[[ -x "$setup" ]] || fail "repository does not contain an executable scripts/setup.sh"

ui_source="$checkout/repository/scripts/terminal-ui.sh"
[[ -r "$ui_source" ]] || fail "repository does not contain the terminal UI helper"
# shellcheck source=/dev/null
source "$ui_source"
ui_banner "UniFi Observer" "Secure native installation"
ui_success "Repository revision downloaded: $REF"

"$setup"

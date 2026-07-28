#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY_URL="${UNIFI_OBSERVER_REPOSITORY_URL:-https://github.com/vypdev/unifi-observer.git}"
REF="${UNIFI_OBSERVER_REF:-master}"

fail() {
  printf 'unifi-observer installer: error: %s\n' "$*" >&2
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

printf 'unifi-observer installer: downloading %s (%s)\n' "$REPOSITORY_URL" "$REF"
git clone --quiet --depth 1 --branch "$REF" "$REPOSITORY_URL" "$checkout/repository"

setup="$checkout/repository/scripts/setup.sh"
[[ -x "$setup" ]] || fail "repository does not contain an executable scripts/setup.sh"

"$setup"

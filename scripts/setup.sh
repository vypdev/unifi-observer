#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIR="${UNIFI_OBSERVER_INSTALL_DIR:-$HOME/.local/share/unifi-observer}"
BIN_DIR="${UNIFI_OBSERVER_BIN_DIR:-$HOME/.local/bin}"
CLI_PATH="$BIN_DIR/unifi-observer"
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

fail() {
  printf 'unifi-observer setup: error: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: scripts/setup.sh

Installs UniFi Observer for the current user into an isolated virtual
environment and starts `unifi-observer configure` unless skipped explicitly.

Environment:
  UNIFI_OBSERVER_INSTALL_DIR     Installation directory
  UNIFI_OBSERVER_BIN_DIR         CLI symlink directory
  UNIFI_OBSERVER_SKIP_CONFIGURE  Set to 1 to install without launching setup
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

[[ "$(uname -s)" == "Linux" ]] || fail "native installation currently supports Linux only"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v systemctl >/dev/null 2>&1 || fail "systemd/systemctl is required"
[[ -f "$REPO_ROOT/pyproject.toml" ]] || fail "run this script from a repository checkout"

python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11 or newer is required")
PY

mkdir -p "$INSTALL_DIR" "$BIN_DIR"
chmod 700 "$INSTALL_DIR"
chmod 755 "$BIN_DIR"

venv="$INSTALL_DIR/.venv"
if [[ ! -x "$venv/bin/python" ]]; then
  python3 -m venv "$venv" || fail "could not create Python virtual environment; install the matching python3-venv package"
fi

"$venv/bin/python" -m pip install --quiet --upgrade "$REPO_ROOT" || fail "could not install the UniFi Observer package"

cli_target="$venv/bin/unifi-observer"
[[ -x "$cli_target" ]] || fail "installed CLI was not found at $cli_target"

if [[ -e "$CLI_PATH" || -L "$CLI_PATH" ]]; then
  [[ -L "$CLI_PATH" && "$(readlink "$CLI_PATH")" == "$cli_target" ]] || fail "$CLI_PATH exists and is not managed by this installer"
else
  ln -s "$cli_target" "$CLI_PATH"
fi

printf 'unifi-observer setup: CLI installed at %s\n' "$CLI_PATH"
printf 'unifi-observer setup: add %s to PATH if the command is not found\n' "$BIN_DIR"

if [[ "${UNIFI_OBSERVER_SKIP_CONFIGURE:-0}" != "1" ]]; then
  [[ -t 0 && -t 1 ]] || fail "interactive configuration requires a terminal; set UNIFI_OBSERVER_SKIP_CONFIGURE=1 to install only"
  exec "$cli_target" configure
fi

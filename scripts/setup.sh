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

run_privileged() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  else
    command -v sudo >/dev/null 2>&1 || fail "sudo is required to install missing system packages"
    sudo "$@"
  fi
}

APT_UPDATED=0
apt_update_once() {
  if (( APT_UPDATED == 0 )); then
    printf 'unifi-observer setup: updating APT metadata\n'
    run_privileged env DEBIAN_FRONTEND=noninteractive apt-get update -qq \
      || fail "apt-get update failed while preparing Python dependencies"
    APT_UPDATED=1
  fi
}

apt_install() {
  apt_update_once
  run_privileged env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@" \
    || fail "could not install required system packages: $*"
}

probe_venv() {
  local probe_dir probe_log
  probe_dir="$(mktemp -d "${TMPDIR:-/tmp}/unifi-observer-venv.XXXXXX")"
  probe_log="$(mktemp "${TMPDIR:-/tmp}/unifi-observer-venv-log.XXXXXX")"
  if python3 -m venv "$probe_dir" >"$probe_log" 2>&1; then
    rm -rf "$probe_dir" "$probe_log"
    return 0
  fi
  VENV_ERROR="$(tr '\n' ' ' < "$probe_log")"
  rm -rf "$probe_dir" "$probe_log"
  return 1
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
command -v systemctl >/dev/null 2>&1 || fail "systemd/systemctl is required"
[[ -f "$REPO_ROOT/pyproject.toml" ]] || fail "run this script from a repository checkout"

if ! command -v python3 >/dev/null 2>&1; then
  command -v apt-get >/dev/null 2>&1 || fail "python3 is missing and apt-get is not available"
  printf 'unifi-observer setup: python3 is missing; installing it\n'
  apt_install python3
fi
command -v python3 >/dev/null 2>&1 || fail "python3 is required after package installation"

python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11 or newer is required; install a newer python3 runtime")
PY

if ! probe_venv; then
  command -v apt-get >/dev/null 2>&1 || fail "Python venv support is unavailable and apt-get is not present (details: $VENV_ERROR)"
  venv_package="$(python3 -c 'import sys; print(f"python{sys.version_info.major}.{sys.version_info.minor}-venv")')"
  if ! apt-cache show "$venv_package" >/dev/null 2>&1; then
    venv_package="python3-venv"
  fi
  printf 'unifi-observer setup: Python venv support is missing; installing %s\n' "$venv_package"
  apt_install "$venv_package"
  probe_venv || fail "Python venv support is still unavailable after installing $venv_package (details: $VENV_ERROR)"
fi

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

if ! commit_marker="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null)"; then
  fail "could not determine the installed repository commit"
fi
printf '%s\n' "$commit_marker" > "$INSTALL_DIR/.unifi-observer-commit.tmp"
mv -f "$INSTALL_DIR/.unifi-observer-commit.tmp" "$INSTALL_DIR/.unifi-observer-commit"
chmod 600 "$INSTALL_DIR/.unifi-observer-commit"

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

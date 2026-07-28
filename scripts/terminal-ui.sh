#!/usr/bin/env bash
# Dependency-free terminal presentation for the installer and native setup.

ui_init() {
  UI_COLOR=0
  UI_UNICODE=0
  if [[ -t 1 && -z "${NO_COLOR:-}" ]] || [[ -n "${FORCE_COLOR:-}" ]]; then
    UI_COLOR=1
  fi
  if [[ "${UNIFI_OBSERVER_ASCII:-0}" != "1" && "${LC_ALL:-${LANG:-}}" == *UTF-8* ]]; then
    UI_UNICODE=1
  fi

  if (( UI_COLOR )); then
    UI_RESET=$'\033[0m'
    UI_BOLD=$'\033[1m'
    UI_CYAN=$'\033[36m'
    UI_GREEN=$'\033[32m'
    UI_YELLOW=$'\033[33m'
    UI_RED=$'\033[31m'
    UI_DIM=$'\033[2m'
  else
    UI_RESET=""
    UI_BOLD=""
    UI_CYAN=""
    UI_GREEN=""
    UI_YELLOW=""
    UI_RED=""
    UI_DIM=""
  fi

  if (( UI_UNICODE )); then
    UI_LINE='═'
    UI_MARK='◈'
    UI_STEP='◆'
    UI_OK='✔'
    UI_WARN='⚠'
    UI_ERR='✖'
  else
    UI_LINE='='
    UI_MARK='*'
    UI_STEP='>'
    UI_OK='OK'
    UI_WARN='!'
    UI_ERR='ERR'
  fi
}

ui_banner() {
  local title="$1"
  local subtitle="${2:-}"
  local line
  line="${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}${UI_LINE}"
  printf '\n%s%s%s\n' "$UI_CYAN" "$line" "$UI_RESET"
  printf '  %s%s%s %s%s%s\n' "$UI_CYAN" "$UI_MARK" "$UI_RESET" "$UI_BOLD$UI_CYAN" "$title" "$UI_RESET"
  [[ -n "$subtitle" ]] && printf '  %s%s%s\n' "$UI_DIM" "$subtitle" "$UI_RESET"
  printf '%s%s%s\n' "$UI_CYAN" "$line" "$UI_RESET"
}

ui_step() { printf '  %s%s%s %s\n' "$UI_CYAN" "$UI_STEP" "$UI_RESET" "$1"; }
ui_info() { printf '  %s%s%s %s\n' "$UI_CYAN" 'i' "$UI_RESET" "$1"; }
ui_success() { printf '  %s%s%s %s\n' "$UI_GREEN" "$UI_OK" "$UI_RESET" "$1"; }
ui_warn() { printf '  %s%s%s %s\n' "$UI_YELLOW" "$UI_WARN" "$UI_RESET" "$1" >&2; }
ui_error() { printf '  %s%s%s %s\n' "$UI_RED" "$UI_ERR" "$UI_RESET" "$1" >&2; }

ui_run() {
  local label="$1"
  shift
  local output_file
  local result
  output_file="$(mktemp "${TMPDIR:-/tmp}/unifi-observer-command.XXXXXX")"

  if [[ ! -t 1 ]]; then
    if "$@"; then
      result=0
    else
      result=$?
    fi
    rm -f "$output_file"
    return "$result"
  fi

  "$@" >"$output_file" 2>&1 &
  local child=$!
  local frames='|/-\\'
  local frame_index=0
  while kill -0 "$child" 2>/dev/null; do
    printf '\r  %s%s%s %s %s' "$UI_CYAN" "${frames:frame_index:1}" "$UI_RESET" "$label" "${UI_DIM}working${UI_RESET}"
    frame_index=$(( (frame_index + 1) % 4 ))
    sleep 0.08
  done

  if wait "$child"; then
    printf '\r\033[2K'
    ui_success "$label"
    rm -f "$output_file"
    return 0
  fi

  printf '\r\033[2K'
  ui_error "$label failed"
  rm -f "$output_file"
  return 1
}

ui_init

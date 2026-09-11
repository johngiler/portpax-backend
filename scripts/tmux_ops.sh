#!/usr/bin/env bash
# PortPax ops dashboard in tmux (API host).
#
# Layout:
#   ┌─────────────────────────────────────────┐
#   │  gunicorn.log + gunicorn-access.log     │  (full width, ccze)
#   ├─────────────┬─────────────┬─────────────┤
#   │ celery.log  │ daphne.log  │    btop     │  (equal width)
#   └─────────────┴─────────────┴─────────────┘
#
# Usage:
#   ./scripts/tmux_ops.sh start|stop|restart|status|attach|run
#
# Install systemd unit (API server, as root):
#   cp scripts/systemd/tmux.service /etc/systemd/system/tmux.service
#   systemctl daemon-reload
#   systemctl enable --now tmux.service
#
# Attach as git:
#   tmux attach -t portpax-ops

set -euo pipefail

SESSION="${PORTPAX_TMUX_SESSION:-portpax-ops}"
GUNICORN_LOG="${PORTPAX_GUNICORN_LOG:-/var/log/gunicorn.log}"
GUNICORN_ACCESS_LOG="${PORTPAX_GUNICORN_ACCESS_LOG:-/var/log/gunicorn-access.log}"
CELERY_LOG="${PORTPAX_CELERY_LOG:-/var/log/celery.log}"
DAPHNE_LOG="${PORTPAX_DAPHNE_LOG:-/var/log/daphne.log}"

colorize_pipe() {
  if command -v ccze >/dev/null 2>&1; then
    echo "| ccze -A"
  else
    echo ""
  fi
}

btop_cmd() {
  if command -v btop >/dev/null 2>&1; then
    echo "btop"
  elif command -v htop >/dev/null 2>&1; then
    echo "htop"
  else
    echo "top"
  fi
}

session_exists() {
  tmux has-session -t "$SESSION" 2>/dev/null
}

cmd_start() {
  if session_exists; then
    echo "tmux session '$SESSION' already running"
    return 0
  fi

  if ! command -v tmux >/dev/null 2>&1; then
    echo "error: tmux is not installed" >&2
    return 1
  fi

  local colorize
  colorize="$(colorize_pipe)"

  # Detached session with a known size so btop layouts before first attach.
  tmux new-session -d -s "$SESSION" -n ops -x 240 -y 60 \
    "tail -n 200 -F ${GUNICORN_LOG} ${GUNICORN_ACCESS_LOG} 2>/dev/null ${colorize}"

  # Bottom row (~45% height): celery | daphne | btop
  tmux split-window -v -t "${SESSION}:ops" -p 45 \
    "tail -n 200 -F ${CELERY_LOG} 2>/dev/null ${colorize}"
  tmux split-window -h -t "${SESSION}:ops" \
    "tail -n 200 -F ${DAPHNE_LOG} 2>/dev/null ${colorize}"
  tmux split-window -h -t "${SESSION}:ops" \
    "$(btop_cmd)"

  # Top = full width; bottom three = equal columns
  tmux select-pane -t "${SESSION}:ops.0"
  tmux select-layout -t "${SESSION}:ops" main-horizontal

  echo "started tmux session '$SESSION'"
  echo "attach: tmux attach -t $SESSION"
}

cmd_stop() {
  if session_exists; then
    tmux kill-session -t "$SESSION"
    echo "stopped tmux session '$SESSION'"
  else
    echo "tmux session '$SESSION' is not running"
  fi
}

cmd_restart() {
  cmd_stop || true
  sleep 0.3
  cmd_start
}

cmd_status() {
  if session_exists; then
    echo "active: $SESSION"
    tmux list-panes -t "${SESSION}:ops" -F \
      '#{pane_index} #{pane_width}x#{pane_height} #{pane_current_command}'
    return 0
  fi
  echo "inactive: $SESSION"
  return 3
}

cmd_attach() {
  if ! session_exists; then
    cmd_start
  fi
  exec tmux attach -t "$SESSION"
}

# Foreground watchdog for systemd Type=simple + Restart=always
cmd_run() {
  cleanup() {
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    exit 0
  }
  trap cleanup TERM INT

  cmd_start
  while session_exists; do
    sleep 5
  done
  echo "tmux session '$SESSION' exited unexpectedly" >&2
  exit 1
}

usage() {
  echo "Usage: $0 {start|stop|restart|status|attach|run}" >&2
  exit 2
}

cmd="${1:-}"
case "$cmd" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_restart ;;
  status) cmd_status ;;
  attach) cmd_attach ;;
  run) cmd_run ;;
  *) usage ;;
esac

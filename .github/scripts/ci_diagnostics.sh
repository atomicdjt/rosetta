#!/usr/bin/env bash
# CI diagnostics for the agent pipelines: a resource sampler, an agent watchdog, and
# a liveness check for both.
#
# Why this is a script and not YAML heredocs: every mechanism written inline so far
# turned out to be a no-op that only revealed itself an hour into a run. This file can
# be `bash -n`-checked, shellcheck'd, and exercised locally before it ever ships.
#
# Why the sampler publishes to a GitHub issue: on this workflow the runner dies with
# "lost communication with the server", and when it does, NOTHING on the runner is
# recoverable -- job logs 404, the run-level log zip comes back empty, and `if: always()`
# upload steps never execute. Cancelling mid-step loses them too. Runs 33561060628,
# 33566733575, 33575461800, 33580251849, 33584601394 and 33588845536 all produced zero
# artifacts for exactly this reason. So the evidence has to leave the runner WHILE it is
# still alive; an issue body edited in place is the cheapest durable channel available.
set -uo pipefail

SAMPLE_SECONDS="${SAMPLE_SECONDS:-30}"
PUBLISH_EVERY="${PUBLISH_EVERY:-2}"   # publish every Nth sample
SYS_LOG="${RUNNER_TEMP:-/tmp}/sys.log"
WATCHDOG_LOG="${RUNNER_TEMP:-/tmp}/watchdog.log"
SAMPLER_LOG="${RUNNER_TEMP:-/tmp}/sampler.log"
ISSUE_FILE="${RUNNER_TEMP:-/tmp}/diag-issue"
BODY_FILE="${RUNNER_TEMP:-/tmp}/diag-body.md"

# Markers let `verify` find these loops by command line without matching itself.
SAMPLER_MARKER="rosetta-ci-sampler"
WATCHDOG_MARKER="rosetta-ci-watchdog"

sample_once() {
  date -u
  free -m 2>/dev/null | head -2
  df -h / | tail -1
  printf 'processes: %s\n' "$(ps -e | wc -l)"
  ps -eo rss,user,comm --sort=-rss 2>/dev/null | head -6
  echo ---
}

publish() {
  [ -s "$ISSUE_FILE" ] || return 0
  local issue
  issue="$(cat "$ISSUE_FILE")"
  {
    printf 'Run %s, updated %s\n\n' "${GITHUB_RUN_ID:-?}" "$(date -u)"
    printf 'Resource samples (newest last):\n\n```\n'
    tail -n 40 "$SYS_LOG" 2>/dev/null | cut -c1-160
    printf '```\n\nWatchdog:\n\n```\n'
    tail -n 25 "$WATCHDOG_LOG" 2>/dev/null | cut -c1-160
    printf '```\n'
  } > "$BODY_FILE"
  gh issue edit "$issue" --repo "$GITHUB_REPOSITORY" --body-file "$BODY_FILE" >/dev/null 2>&1 || true
}

start_sampler() {
  : > "$SYS_LOG"
  local url
  url="$(gh issue create --repo "$GITHUB_REPOSITORY" \
          --title "[ci-diagnostics] ${GITHUB_WORKFLOW:-run} ${GITHUB_RUN_ID:-?}" \
          --body 'Collecting runner diagnostics; this issue is updated in place.' 2>/dev/null)" || true
  if [ -n "$url" ]; then
    printf '%s\n' "${url##*/}" > "$ISSUE_FILE"
    echo "diagnostics issue: $url"
  else
    echo "::warning::could not open the diagnostics issue; samples stay on the runner only"
  fi

  # Backgrounded so one loop spans the whole agent step. Verified: orphans DO survive
  # step end here (run 33588845536's `Verify watchdog alive` passed).
  nohup bash -c "
    # $SAMPLER_MARKER
    n=0
    while true; do
      '$0' sample-once >> '$SYS_LOG' 2>&1
      n=\$(( n + 1 ))
      [ \$(( n % $PUBLISH_EVERY )) -eq 0 ] && '$0' publish
      sleep $SAMPLE_SECONDS
    done
  " > "$SAMPLER_LOG" 2>&1 &
  echo "sampler started (every ${SAMPLE_SECONDS}s, publishing every ${PUBLISH_EVERY} samples)"
}

# Kill the agent so the COMPOSITE action's step fails like any ordinary step failure and
# the job carries on to the upload steps. Step-level `timeout-minutes` cannot do this --
# Actions ignores it on composite actions -- and the job cap cancels the job outright.
#
# Everything here is deliberately loud. The previous version used `pkill … || true`,
# which swallowed whatever went wrong; all that was known afterwards was that the agent
# outlived a 3-minute cap. Now the process table, the chosen PIDs and every kill error
# land in the log the heartbeat publishes.
kill_agent() {
  echo "=== process table at $(date -u) ==="
  # Truncated: this goes into an issue body, and one unclipped Electron command line
  # is several kilobytes on its own.
  ps -eo pid,ppid,user,comm,args 2>/dev/null \
    | grep -i -e codex -e claude | grep -v grep | cut -c1-200 | head -25

  # `[c]` keeps each pattern from matching this script's own command line.
  local pids=""
  for pat in 'main.js run-codex-exe[c]' '[c]odex-x86_64' '[c]odex exec' 'claude-code-actio[n]'; do
    local hit
    hit="$(pgrep -f "$pat" 2>/dev/null | grep -v "^$$\$" || true)"
    [ -n "$hit" ] && echo "pattern '$pat' matched: $(echo "$hit" | tr '\n' ' ')"
    pids="$pids $hit"
  done
  pids="$(echo "$pids" | tr ' ' '\n' | grep -v '^$' | sort -u | tr '\n' ' ')"

  if [ -z "${pids// /}" ]; then
    echo "NO MATCH: nothing to kill -- the patterns are wrong, see the table above"
    return 0
  fi

  echo "TERM ->$pids"
  # No `|| true`: a permission error here is the answer, so let it print.
  for p in $pids; do kill -TERM "$p"; done
  sleep 15
  for p in $pids; do
    if kill -0 "$p" 2>/dev/null; then
      echo "survived TERM, sending KILL -> $p"
      kill -KILL "$p"
    fi
  done
  echo "=== done at $(date -u) ==="
}

start_watchdog() {
  local mins="${AGENT_TIMEOUT_MINUTES:?AGENT_TIMEOUT_MINUTES is required}"
  : > "$WATCHDOG_LOG"
  nohup bash -c "
    # $WATCHDOG_MARKER
    sleep \$(( $mins * 60 ))
    echo '::error::agent exceeded ${mins}m; terminating so the trace can upload'
    '$0' kill-agent
  " >> "$WATCHDOG_LOG" 2>&1 &
  echo "watchdog armed: ${mins} minutes"
}

# A background loop that dies with the step that started it is worse than none: it looks
# like protection and silently is not. Fail here, in seconds and with logs, rather than
# discovering it an hour in.
verify() {
  local rc=0
  if ! pgrep -f "$WATCHDOG_MARKER" >/dev/null 2>&1; then
    echo "::error::watchdog is not running"; rc=1
  else
    echo "watchdog alive"
  fi
  # `runner.debug` is "1"; accept "true" as well so a human setting it by hand is not
  # silently ignored.
  if [ "${DIAGNOSTICS:-}" = "1" ] || [ "${DIAGNOSTICS:-}" = "true" ]; then
    if ! pgrep -f "$SAMPLER_MARKER" >/dev/null 2>&1; then
      echo "::error::sampler is not running"; rc=1
    else
      echo "sampler alive"
    fi
    if [ -s "$ISSUE_FILE" ]; then
      echo "diagnostics issue: #$(cat "$ISSUE_FILE")"
    else
      echo "::warning::no diagnostics issue; nothing will survive a runner death"
    fi
  fi
  return $rc
}

cmd="${1:-}"
if [ -z "$cmd" ]; then
  echo "usage: ci_diagnostics.sh {start-sampler|start-watchdog|verify|sample-once|publish|kill-agent}" >&2
  exit 2
fi

case "$cmd" in
  start-sampler)  start_sampler ;;
  start-watchdog) start_watchdog ;;
  verify)         verify ;;
  sample-once)    sample_once ;;
  publish)        publish ;;
  kill-agent)     kill_agent ;;
  *) echo "unknown subcommand: $cmd" >&2; exit 2 ;;
esac

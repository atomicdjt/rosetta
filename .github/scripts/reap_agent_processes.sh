#!/usr/bin/env bash
# Terminate anything the Codex agent step left behind, so the job can finalise.
#
# WHY THIS EXISTS
#
# `openai/codex-action` leaves processes running after its step reports success --
# at minimum a `codex-responses-api-proxy`, plus the `codex exec` tree and its
# `codex-code-mode` children. A GitHub runner cannot finalise a job while a process
# still holds the step's output pipe, so the job simply stops making progress:
#
#   * triage runs where the agent halted in ~40s finished cleanly in ~75s;
#   * triage runs where the agent did real work hung and were cancelled at the job
#     cap (runs 33566733575, 33571030280, 33573223448 -- 35, 65, 65 minutes);
#   * analysis runs hung until GitHub declared the runner lost at ~62 minutes with
#     "the hosted runner lost communication with the server" (33561060628,
#     33575461800, 33580251849, 33584601394, 33649501514);
#   * the one analysis run whose process tree was killed mid-step finalised normally
#     in 3m10s (33648971702).
#
# So the ~60 minutes was never a timeout doing its job -- it was GitHub noticing a
# runner that had stopped talking. Reaping the leftovers removes the hang itself.
#
# Runs as `if: always()` straight after the agent step: a normal, ordinary cleanup
# step, not a timeout mechanism.
set -uo pipefail

echo "Leftover agent processes:"
# `[c]` keeps each pattern from matching this script's own command line.
found=0
for pat in 'codex-responses-api-prox[y]' 'main.js run-codex-exe[c]' '[c]odex-x86_64' '[c]odex exec' 'codex-code-mod[e]'; do
  pids="$(pgrep -f "$pat" 2>/dev/null || true)"
  [ -z "$pids" ] && continue
  found=1
  echo "  $pat -> $(echo "$pids" | tr '\n' ' ')"
  # Errors are NOT swallowed: part of the tree runs under sudo, and a permission
  # failure here is something we need to see rather than silently tolerate.
  for p in $pids; do kill -TERM "$p" 2>&1 || true; done
done

if [ "$found" -eq 0 ]; then
  echo "  none"
  exit 0
fi

sleep 5
for pat in 'codex-responses-api-prox[y]' 'main.js run-codex-exe[c]' '[c]odex-x86_64' '[c]odex exec' 'codex-code-mod[e]'; do
  for p in $(pgrep -f "$pat" 2>/dev/null || true); do
    echo "  survived TERM, sending KILL -> $p"
    kill -KILL "$p" 2>&1 || true
  done
done
echo "Cleanup done."

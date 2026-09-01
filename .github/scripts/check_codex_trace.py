#!/usr/bin/env python3
"""Post-run guard for the Codex branch of the Rosetta pipelines.

The Codex counterpart of `check_trace.py`. It answers only ONE of that script's
two questions:

  1. did the run mutate anything?  -- checked here
  2. did the main agent background a subagent and abandon it?  -- NOT checked

Check 2 has no Codex analogue: the Codex plugin has no subagent mechanism, so
there is nothing to background and nothing to strand. The Codex path therefore
carries less post-run verification than the Claude path by construction, not by
omission.

Check 1 is skipped with --allow-no-op, for the same reason as in `check_trace.py`:
board-driven pipelines are pulled by board state that guarantees work exists, so
doing nothing is a failure; triage is event-driven and may legitimately have
nothing to say.

Input is the Codex rollout tree (`$CODEX_HOME/sessions`), one JSON object per line.
Only `response_item.function_call` records for a shell tool are inspected; the
mutating-command vocabulary is shared with `check_trace.py` so both branches are
held to the same definition of "did real work".
"""
import json
import os
import sys

from check_trace import MUTATING

# Codex reaches the shell through more than one tool name across CLI versions, and
# the argument key differs with it: `exec_command` carries a `cmd` STRING (see the
# recorded sample at docs/hooks/codex-019f0634-transcript.jsonl), while `shell` and
# `local_shell_call` carry a `command` ARRAY, usually ["bash", "-lc", "<script>"].
SHELL_TOOLS = ("shell", "exec_command", "local_shell_call", "container.exec")


def rollouts(path):
    """Every rollout file under `path`, or `path` itself when it is a file."""
    if os.path.isfile(path):
        return [path]
    found = []
    for root, _dirs, names in os.walk(path):
        found += [
            os.path.join(root, n) for n in sorted(names) if n.endswith(".jsonl")
        ]
    return found


def commands(path):
    """Shell command strings the agent executed, in order."""
    out = []
    with open(path, errors="surrogateescape") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                # A rollout is appended to live; a torn last line is not a finding.
                continue
            if not isinstance(rec, dict) or rec.get("type") != "response_item":
                continue
            payload = rec.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("type") != "function_call":
                continue
            if payload.get("name") not in SHELL_TOOLS:
                continue
            args = payload.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            if not isinstance(args, dict):
                continue
            raw = args.get("cmd", args.get("command"))
            if isinstance(raw, str):
                out.append(raw)
            elif isinstance(raw, list):
                parts = [p for p in raw if isinstance(p, str)]
                # Match the wrapper's own argv AND each element: `gh issue create ...`
                # arrives as the last element of ["bash", "-lc", "<script>"], and a
                # direct argv form has it spread across the whole list.
                out += parts
                out.append(" ".join(parts))
    return out


def main(path, require_mutation=True):
    files = rollouts(path)
    if not files:
        print(
            "::error::no Codex rollout found under %s -- the Codex step did not run"
            % path
        )
        return 1

    mutating = []
    for f in files:
        for cmd in commands(f):
            if MUTATING.match(cmd):
                mutating.append(cmd.strip()[:120])

    print("Codex rollout files inspected: %d" % len(files))
    print("issue-mutating commands executed: %d" % len(mutating))
    for c in mutating:
        print("  %s" % c)

    if require_mutation and not mutating:
        print(
            "::error::The run changed nothing: no issue, pull-request or board "
            "mutation was executed."
        )
        return 1
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("usage: check_codex_trace.py <sessions-dir> [--allow-no-op]",
              file=sys.stderr)
        sys.exit(2)
    sys.exit(main(args[0], require_mutation="--allow-no-op" not in sys.argv[1:]))

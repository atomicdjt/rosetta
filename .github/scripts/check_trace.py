#!/usr/bin/env python3
"""Post-run guard for the repo-analysis pipeline.

Fails the job on the two silent-failure modes the traces exposed:
  1. the main agent backgrounded a subagent (report can never arrive in -p)
  2. the run never attempted to create or update an issue

Both checks parse the SDK message array structurally. Substring greps do not
work here: the prompt text is itself inside the trace (via Read tool_results),
so a grep for "gh issue create" matches on every run, including runs that
never executed it.
"""
import json
import re
import sys

MUTATING = re.compile(
    r"""^\s*gh\s+(issue\s+(create|edit|comment|close)|project\s+item-(add|edit))\b"""
)


def blocks(msg):
    content = (msg.get("message") or {}).get("content")
    return content if isinstance(content, list) else []


def main(path):
    with open(path) as fh:
        msgs = json.load(fh)

    # Main agent only: parent_tool_use_id is null. A nested subagent that
    # backgrounds its own child is a prompt-compliance issue, not the fatal
    # one -- it does not end the job -- so scoping here avoids false failures.
    main_agent_dispatches = {}
    mutating = []
    for msg in msgs:
        is_main = msg.get("parent_tool_use_id") is None
        for b in blocks(msg):
            if b.get("type") == "tool_use":
                if is_main and b.get("name") in ("Agent", "Task"):
                    main_agent_dispatches[b["id"]] = b["input"].get("description", "")
                elif b.get("name") == "Bash":
                    cmd = b.get("input", {}).get("command", "")
                    if MUTATING.match(cmd):
                        mutating.append(cmd.strip()[:120])

    backgrounded, orphaned = [], []
    for msg in msgs:
        for b in blocks(msg):
            if b.get("type") != "tool_result":
                continue
            tid = b.get("tool_use_id")
            if tid not in main_agent_dispatches:
                continue
            text = json.dumps(b.get("content"))
            if "Async agent launched successfully" in text:
                backgrounded.append(main_agent_dispatches.pop(tid))
            else:
                main_agent_dispatches.pop(tid)
    orphaned = list(main_agent_dispatches.values())

    failures = []
    if backgrounded:
        failures.append(
            "%d subagent(s) were backgrounded by the main agent and abandoned "
            "(their reports can never arrive in headless mode): %s"
            % (len(backgrounded), "; ".join(backgrounded))
        )
    if orphaned:
        failures.append(
            "%d subagent dispatch(es) never returned -- the job was torn down "
            "while they were still running: %s"
            % (len(orphaned), "; ".join(orphaned))
        )
    if not mutating:
        failures.append(
            "Phase 3 never ran: no gh issue create/edit/comment/close or "
            "gh project item-add/item-edit command was executed."
        )

    print("issue-mutating commands executed: %d" % len(mutating))
    for c in mutating:
        print("  %s" % c)
    print("main-agent subagent dispatches: backgrounded=%d, orphaned=%d"
          % (len(backgrounded), len(orphaned)))

    for f in failures:
        print("::error::%s" % f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))

"""Tests for the GitHub Projects v2 board loader.

Run: python3 -m pytest .github/scripts/test_load_stories.py
"""
import importlib.util
import json
import pathlib

import pytest

spec = importlib.util.spec_from_file_location(
    "load_stories", pathlib.Path(__file__).with_name("load_stories.py")
)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def issue(number, status=None, priority=None, repo="griddynamics/rosetta", type_="Issue"):
    item = {
        "id": f"item-{number}",
        "content": {
            "type": type_,
            "number": number,
            "title": f"issue {number}",
            "repository": repo,
        },
    }
    if status is not None:
        item["status"] = status
    if priority is not None:
        item["priority"] = priority
    return item


# ── Priority gate (planner only) ────────────────────────────────────────────────

@pytest.mark.parametrize("priority", ["High", "P0", "P1", "P2", "Medium", "Urgent"])
def test_set_non_low_priority_is_plannable(priority):
    assert module.is_plannable(priority) is True


@pytest.mark.parametrize("priority", [None, "", "   ", "Low", "low", "LOW", "P3", "p4"])
def test_unset_or_low_priority_is_not_plannable(priority):
    assert module.is_plannable(priority) is False


def test_priority_gate_applies_to_backlog_only():
    plan, impl = module.collect_matrices({"items": [
        issue(1, status="Backlog", priority="P1"),
        issue(2, status="Backlog", priority="Low"),
        issue(3, status="Backlog"),                    # unset
        issue(4, status="Ready"),                      # unset, must still implement
        issue(5, status="Ready", priority="Low"),      # low, must still implement
    ]})
    assert [e["issue_number"] for e in plan] == [1]
    assert [e["issue_number"] for e in impl] == [4, 5]


def test_require_priority_field_exits_when_missing():
    with pytest.raises(SystemExit) as exc:
        module.require_priority_field({"fields": [{"name": "Status"}]})
    assert exc.value.code == 1


def test_require_priority_field_passes_when_present():
    assert module.require_priority_field(
        {"fields": [{"name": "Status"}, {"name": "Priority"}]}
    ) is None


# ── Status selection ────────────────────────────────────────────────────────────

def test_only_backlog_and_ready_are_selected():
    plan, impl = module.collect_matrices({"items": [
        issue(1, status="Backlog", priority="P1"),
        issue(2, status="Ready"),
        issue(3, status="In progress", priority="P1"),
        issue(4, status="In review", priority="P1"),
        issue(5, status="Done", priority="P1"),
        issue(6, priority="P1"),                       # status unset
    ]})
    assert [e["issue_number"] for e in plan] == [1]
    assert [e["issue_number"] for e in impl] == [2]


def test_status_match_is_case_and_whitespace_sensitive():
    plan, impl = module.collect_matrices({"items": [
        issue(1, status="backlog", priority="P1"),
        issue(2, status="Backlog ", priority="P1"),
    ]})
    assert plan == [] and impl == []


# ── Content filtering ───────────────────────────────────────────────────────────

def test_pull_requests_and_drafts_are_excluded():
    plan, impl = module.collect_matrices({"items": [
        issue(1, status="Backlog", priority="P1", type_="PullRequest"),
        issue(2, status="Ready", type_="DraftIssue"),
    ]})
    assert plan == [] and impl == []


def test_items_from_other_repositories_are_excluded():
    plan, _ = module.collect_matrices({"items": [
        issue(1, status="Backlog", priority="P1", repo="griddynamics/other"),
    ]})
    assert plan == []


def test_null_content_does_not_crash():
    """gh emits "content": null for cards the token cannot resolve."""
    plan, _ = module.collect_matrices({"items": [
        {"id": "x", "content": None, "status": "Backlog"},
        issue(1, status="Backlog", priority="P1"),
    ]})
    assert [e["issue_number"] for e in plan] == [1]


# ── Matrix shape ────────────────────────────────────────────────────────────────

def test_empty_matrix_emits_skip_sentinel():
    parsed = json.loads(module.build_matrix([]))
    assert parsed["include"][0]["issue_title"] == "__skip__"


def test_title_is_truncated_and_sanitized():
    plan, _ = module.collect_matrices({"items": [{
        "id": "item-1",
        "status": "Backlog",
        "priority": "P1",
        "content": {
            "type": "Issue", "number": 1, "repository": "griddynamics/rosetta",
            "title": 'a"b' + "\n" + "x" * 200,
        },
    }]})
    title = plan[0]["issue_title"]
    assert len(title) == 80
    assert '"' not in title and "\n" not in title


def test_status_field_extraction():
    field_id, options = module.extract_status_field({"fields": [
        {"id": "F1", "name": "Status", "options": [
            {"id": "o1", "name": "Backlog"}, {"id": "o2", "name": "Ready"},
        ]},
    ]})
    assert field_id == "F1"
    assert options == {"Backlog": "o1", "Ready": "o2"}

"""Merge and arbitrate critic issues."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple


SEVERITY_ORDER = {"blocker": 4, "major": 3, "minor": 2, "nit": 1}


@dataclass
class MergeResult:
    merged: List[Dict[str, Any]]
    decisions: List[Dict[str, Any]]


def _normalize_text(text: str) -> str:
    return "".join(text.split()).lower()[:200]


def _issue_key(issue: Dict[str, Any]) -> str:
    issue_type = issue.get("type", "")
    keys = ",".join(sorted(issue.get("related_memory_keys", []) or []))
    evidence = issue.get("evidence", [])
    quote = ""
    if evidence and isinstance(evidence, list):
        quote = evidence[0].get("quote", "") if isinstance(evidence[0], dict) else str(evidence[0])
    return f"{issue_type}|{keys}|{_normalize_text(quote)}"


def merge_issues(
    issues_by_provider: Dict[str, List[Dict[str, Any]]],
    arbiter: Callable[[List[Dict[str, Any]]], Tuple[Dict[str, Any], str]] | None = None,
) -> MergeResult:
    grouped: Dict[str, List[Tuple[str, Dict[str, Any]]]] = defaultdict(list)

    for provider, issues in issues_by_provider.items():
        for issue in issues:
            grouped[_issue_key(issue)].append((provider, issue))

    merged: List[Dict[str, Any]] = []
    decisions: List[Dict[str, Any]] = []

    for key, items in grouped.items():
        # select highest severity or arbitrate if conflicts
        best = None
        best_provider = None
        severities = {issue.get("severity", "minor") for _, issue in items}
        suggestions = {issue.get("fix_suggestion", "").strip() for _, issue in items}
        conflict = len(severities) > 1 or len(suggestions) > 1

        if arbiter and conflict:
            chosen, reason = arbiter([issue for _, issue in items])
            best = chosen
            best_provider = "arbiter"
        else:
            reason = "selected highest severity"
            for provider, issue in items:
                sev = SEVERITY_ORDER.get(issue.get("severity", "minor"), 0)
                if best is None or sev > SEVERITY_ORDER.get(best.get("severity", "minor"), 0):
                    best = issue
                    best_provider = provider

        if best is None:
            continue

        # merge evidence
        evidence = []
        for _, issue in items:
            evidence.extend(issue.get("evidence", []) or [])
        best = dict(best)
        best["evidence"] = evidence[:5]

        merged.append(best)
        if len(items) > 1:
            decisions.append(
                {
                    "issue_key": key,
                    "providers": [p for p, _ in items],
                    "selected_provider": best_provider,
                    "reason": reason,
                }
            )

    return MergeResult(merged=merged, decisions=decisions)


def write_merge_outputs(result: MergeResult, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "issues_merged.json").write_text(
        json.dumps(result.merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "issues_decisions.json").write_text(
        json.dumps(result.decisions, ensure_ascii=False, indent=2), encoding="utf-8"
    )

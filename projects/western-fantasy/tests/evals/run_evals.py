"""Run lightweight consistency evals without model calls."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List

import yaml

PROJECT_PATH = Path(__file__).resolve().parents[2]

import sys

sys.path.insert(0, str(PROJECT_PATH))

from temporal_fact_store import TemporalFactStore, Fact
from hard_state_checker import check_hard_state
from consistency_checker import run_consistency_check


def load_cases(path: Path) -> List[Dict[str, Any]]:
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        cases.append(json.loads(line))
    return cases


def load_canon(project_path: Path) -> Dict[str, Any]:
    canon_path = project_path / "canon.yaml"
    if not canon_path.exists():
        return {}
    return yaml.safe_load(canon_path.read_text(encoding="utf-8")) or {}


def snapshot_for_state_manager(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    state = {"system": {"warehouse": {}}}
    entries = []
    warehouse = snapshot.get("system.warehouse", {})
    if "accessible" in warehouse:
        state["system"]["warehouse"]["accessible"] = warehouse["accessible"]
        entries.append(
            {
                "path": "system.warehouse.accessible",
                "value": warehouse["accessible"],
                "evidence": "eval_seed",
            }
        )
    return {"state": state, "entries": entries}


def run_case(case: Dict[str, Any], canon: Dict[str, Any]) -> Dict[str, Any]:
    with TemporaryDirectory() as tmp:
        store = TemporalFactStore(Path(tmp) / "facts.db")
        for fact in case.get("history_facts", []):
            store.upsert_facts(
                case.get("chapter", 1) - 1,
                [
                    Fact(
                        subject=fact.get("subject"),
                        predicate=fact.get("predicate"),
                        object_value=fact.get("value"),
                        valid_from_chapter=0,
                        source_chapter=0,
                        hard_flag=bool(fact.get("hard", True)),
                    )
                ],
            )

        chapter_num = int(case.get("chapter", 1))
        snapshot = store.get_snapshot(chapter_num - 1)
        draft = case.get("draft", "")

        issues = check_hard_state(draft, snapshot, canon)
        consistency = run_consistency_check(snapshot_for_state_manager(snapshot), {}, draft)
        for issue in consistency.get("issues", []):
            if issue.get("severity") == "error":
                issues.append(
                    {
                        "type": "state_violation",
                        "severity": "blocker",
                        "evidence": [{"quote": issue.get("evidence_new", ""), "chapter_pos": "unknown"}],
                        "related_memory_keys": [issue.get("rule_id", "")],
                        "fix_suggestion": "补充剧情解释或改写相关段落。",
                        "requires_rewrite_scope": "paragraph",
                    }
                )

        expect = case.get("expect", {})
        ok = True
        blocker_keys = set(expect.get("blocker_keys", []))
        types = set(expect.get("types", []))

        if blocker_keys:
            found = set()
            for issue in issues:
                if issue.get("severity") in {"blocker", "major"}:
                    for key in issue.get("related_memory_keys", []):
                        if key in blocker_keys:
                            found.add(key)
            ok = ok and found == blocker_keys

        if types:
            present = {issue.get("type") for issue in issues}
            ok = ok and types.issubset(present)

        return {"id": case.get("id"), "ok": ok, "issues": issues}


def main():
    cases_path = PROJECT_PATH / "tests" / "evals" / "novel_consistency_cases.jsonl"
    canon = load_canon(PROJECT_PATH)
    cases = load_cases(cases_path)

    results = [run_case(case, canon) for case in cases]
    failed = [r for r in results if not r["ok"]]

    print("Eval results:")
    for result in results:
        status = "PASS" if result["ok"] else "FAIL"
        print(f"- {result['id']}: {status}")

    if failed:
        print("\nFailures:")
        for result in failed:
            print(f"- {result['id']} issues: {len(result['issues'])}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""一致性检查：输出结构化问题与修复指令"""

from typing import Any, Dict, List

from story_state_manager import StoryStateManager



def run_consistency_check(
    snapshot: Dict[str, Any],
    plan: Dict[str, Any],
    draft: str,
) -> Dict[str, Any]:
    manager = StoryStateManager()
    issues = manager.validate_chapter(draft, snapshot)
    repairs: List[Dict[str, Any]] = []

    for issue in issues:
        if issue.get("rule_id") == "system.warehouse.strict_access" and issue.get("severity") == "error":
            repairs.append(
                {
                    "rule_id": issue.get("rule_id"),
                    "options": [
                        {
                            "type": "rewrite_to_fail_access",
                            "hint": "将成功访问改写为失败/权限不足，并删除取物收益。",
                        },
                        {
                            "type": "add_unlock_event",
                            "hint": "在首次成功访问前补充解锁/升级/获得权限桥段，并同步提示解锁。",
                        },
                    ],
                }
            )

    return {"issues": issues, "repairs": repairs}

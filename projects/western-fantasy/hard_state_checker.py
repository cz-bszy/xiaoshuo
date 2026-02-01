"""Hard state and style checks."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from story_state_manager import WAREHOUSE_FAILURE, WAREHOUSE_SUCCESS, WAREHOUSE_KEYWORDS


STYLE_BANNED_PATTERNS = [
    r"优点",
    r"缺点",
    r"不足[:：]",
    r"不足之处",
    r"状态面板",
    r"能力面板",
    r"属性面板",
    r"状态如下",
    r"分析[:：]",
    r"分析如下",
    r"总结[:：]",
    r"总结如下",
]


def check_hard_state(draft: str, hard_snapshot: Dict[str, Any], canon: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []

    # HARD_RULE checks
    for rule in canon.get("HARD_RULE", []):
        key = rule.get("key")
        value = rule.get("value")
        keywords = rule.get("violation_keywords", [])
        if key == "system.warehouse.accessible" and value is False:
            trigger = any(k in draft for k in (keywords or WAREHOUSE_KEYWORDS))
            success = any(k in draft for k in WAREHOUSE_SUCCESS)
            failure = any(k in draft for k in WAREHOUSE_FAILURE)
            if trigger and success and not failure:
                issues.append(
                    {
                        "type": "state_violation",
                        "severity": "blocker",
                        "evidence": [{"quote": _find_quote(draft, keywords), "chapter_pos": "unknown"}],
                        "related_memory_keys": [key],
                        "fix_suggestion": "加入解锁事件或改写为访问失败。",
                        "requires_rewrite_scope": "paragraph",
                    }
                )

    # Style bans
    for pattern in STYLE_BANNED_PATTERNS:
        if re.search(pattern, draft):
            issues.append(
                {
                    "type": "style_meta",
                    "severity": "major",
                    "evidence": [{"quote": pattern, "chapter_pos": "unknown"}],
                    "related_memory_keys": [],
                    "fix_suggestion": "改为通过行动/对话/细节呈现，不使用条目分析。",
                    "requires_rewrite_scope": "paragraph",
                }
            )
            break

    # Name drift (canonical required)
    canonical = ""
    aliases: List[str] = []
    for fact in canon.get("SOFT_FACT", []):
        if fact.get("key") == "protagonist.canonical_name":
            canonical = fact.get("value", "")
        if fact.get("key") == "protagonist.aliases":
            aliases = fact.get("value", []) or []

    if canonical:
        alias_hits = [a for a in aliases if a and a in draft]
        if alias_hits and canonical not in draft:
            issues.append(
                {
                    "type": "name_drift",
                    "severity": "major",
                    "evidence": [{"quote": alias_hits[0], "chapter_pos": "unknown"}],
                    "related_memory_keys": ["protagonist.canonical_name"],
                    "fix_suggestion": "叙述中使用 canonical_name，别名仅作为对白/绰号出现，并说明关系。",
                    "requires_rewrite_scope": "paragraph",
                }
            )

    return issues


def _find_quote(text: str, keywords: List[str]) -> str:
    for line in text.splitlines():
        for k in keywords:
            if k in line:
                return line.strip()[:200]
    return keywords[0] if keywords else ""

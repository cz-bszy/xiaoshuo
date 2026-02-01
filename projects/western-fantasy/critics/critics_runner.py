"""Run multiple critic models in parallel and collect issues."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from llm_clients import OpenAICompatibleClient, ProviderConfig, safe_json_loads


ISSUE_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": ["string", "null"]},
                    "type": {"type": "string"},
                    "severity": {"type": "string"},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "quote": {"type": "string"},
                                "chapter_pos": {"type": "string"},
                            },
                            "required": ["quote"],
                        },
                    },
                    "related_memory_keys": {"type": "array", "items": {"type": "string"}},
                    "fix_suggestion": {"type": "string"},
                    "requires_rewrite_scope": {"type": "string"},
                },
                "required": ["type", "severity", "evidence", "fix_suggestion", "requires_rewrite_scope"],
            },
        }
    },
    "required": ["issues"],
}


@dataclass
class CriticResult:
    provider: str
    issues: List[Dict[str, Any]]
    raw_text: str
    error: Optional[str] = None


def _critic_prompt(draft: str, canon_summary: str, state_snapshot: Dict[str, Any], context_excerpt: str) -> List[Dict[str, str]]:
    snapshot_text = json.dumps(state_snapshot, ensure_ascii=False, indent=2)
    system = "你是严苛的小说审稿人。只输出 JSON，不要解释。"
    user = f"""
请审阅以下章节草稿，输出 issues JSON。

## Canon 摘要
{canon_summary}

## Hard State Snapshot
{snapshot_text}

## Context Excerpt
{context_excerpt}

## 章节草稿
{draft}

输出要求：
- 严格 JSON，格式：{{"issues": [ ... ]}}
- 每条 issue 必须有 evidence.quote
- severity 只能是 blocker/major/minor/nit
- type 只能用：continuity/state_violation/timeline/character_voice/style_meta/plot_hole/redundancy/name_drift
- fix_suggestion 给出最小修复建议
- requires_rewrite_scope 只能是 line/paragraph/scene
- 如果正文出现提纲/清单/场景安排/写作要点/基本信息等非叙事结构，必须给出 style_meta issue（severity=major）
- 章节末尾 State Diff 的 JSON 代码块是系统要求，不作为问题
- 若正文出现 Markdown 标题（#、##、###）或“场景一/二”等小节标题，必须给出 style_meta issue（severity=major），修复建议应为“删除标题，改为连续叙事”，不要建议新增标题
"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def run_critics(
    draft: str,
    canon_summary: str,
    state_snapshot: Dict[str, Any],
    context_excerpt: str,
    critic_configs: Dict[str, ProviderConfig],
    max_workers: int = 3,
    output_dir: Optional[Path] = None,
) -> List[CriticResult]:
    results: List[CriticResult] = []
    if not critic_configs:
        return results

    output_dir.mkdir(parents=True, exist_ok=True) if output_dir else None

    def run_single(name: str, config: ProviderConfig) -> CriticResult:
        import time

        client = OpenAICompatibleClient(config)
        messages = _critic_prompt(draft, canon_summary, state_snapshot, context_excerpt)

        for attempt in range(3):
            try:
                raw = client.chat(messages, response_format={"type": "json_object"})
                data = safe_json_loads(raw)
                issues = data.get("issues", []) if isinstance(data, dict) else []
                return CriticResult(provider=name, issues=issues, raw_text=raw)
            except Exception as e:
                err = str(e)
                if attempt < 2 and ("429" in err or "RateLimit" in err):
                    time.sleep(10 * (attempt + 1))
                    continue
                return CriticResult(provider=name, issues=[], raw_text="", error=err)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(run_single, name, config): name
            for name, config in critic_configs.items()
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)

    if output_dir:
        for result in results:
            path = output_dir / f"issues_raw_{result.provider}.json"
            payload = {
                "provider": result.provider,
                "error": result.error,
                "issues": result.issues,
            }
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return results

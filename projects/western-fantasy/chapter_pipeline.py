"""Chapter pipeline: draft -> review -> revise -> finalize -> commit."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from chapter_catalog import get_chapter_info
from critics.critics_runner import run_critics
from critics.issues_merger import merge_issues, write_merge_outputs
from hard_state_checker import check_hard_state
from llm_clients import OpenAICompatibleClient, ProviderConfig, load_provider_configs, safe_json_loads
from memory_bank_manager import MemoryBankManager
from story_memory_adapter import StoryMemoryAdapter
from consistency_checker import run_consistency_check
from temporal_fact_store import Fact, TemporalFactStore
from story_state_manager import StoryStateManager


@dataclass
class PipelineConfig:
    writer_provider: str
    critic_providers: List[str]
    critics_enabled: bool
    critics_workers: int
    use_memory: bool
    use_hard_checker: bool
    use_consistency_checker: bool


class ChapterPipeline:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.repo_root = project_path.parents[1]
        self.config = self._load_config()
        self.providers = load_provider_configs(project_path / "configs" / "providers.yaml")
        self.writer_client = self._build_writer()
        self.critic_configs = self._build_critics()

        self.state_manager = StoryStateManager(project_path=project_path)
        self.fact_store = TemporalFactStore(project_path / "data" / "facts.db")
        self.memory_bank = MemoryBankManager(project_path)
        self.memory_adapter = StoryMemoryAdapter(clear_db=False) if self.config.use_memory else None
        self.canon = self._load_canon()

        self.pipeline_root = project_path / "pipeline" / "chapters"
        self.pipeline_root.mkdir(parents=True, exist_ok=True)
        self.memory_commits = project_path / "memory_commits"
        self.memory_commits.mkdir(parents=True, exist_ok=True)

        self._ensure_seed_facts()

    def _load_config(self) -> PipelineConfig:
        cfg = yaml.safe_load((self.project_path / "config.yaml").read_text(encoding="utf-8")) or {}
        writing = cfg.get("writing", {})
        critics = cfg.get("critics", {})
        review = cfg.get("review", {})
        return PipelineConfig(
            writer_provider=writing.get("provider", "deepseek"),
            critic_providers=critics.get("providers", ["kimi", "glm"]),
            critics_enabled=critics.get("enabled", True),
            critics_workers=int(critics.get("max_workers", 2)),
            use_memory=bool(writing.get("use_memory", False)),
            use_hard_checker=bool(review.get("use_hard_checker", True)),
            use_consistency_checker=bool(review.get("use_consistency_checker", True)),
        )

    def _build_writer(self) -> OpenAICompatibleClient:
        config = self.providers.get(self.config.writer_provider)
        if not config:
            raise RuntimeError(f"Writer provider missing: {self.config.writer_provider}")
        return OpenAICompatibleClient(config)

    def _build_critics(self) -> Dict[str, ProviderConfig]:
        if not self.config.critics_enabled:
            return {}
        configs = {}
        for name in self.config.critic_providers:
            if name in self.providers:
                base = self.providers[name]
                model = self._get_provider_model(name, "critic")
                configs[name] = ProviderConfig(
                    name=name,
                    base_url=base.base_url,
                    api_key=base.api_key,
                    model=model,
                    temperature=base.temperature,
                    max_tokens=base.max_tokens,
                    thinking_mode=base.thinking_mode,
                )
        return configs

    def _get_provider_model(self, provider: str, role: str) -> str:
        data = yaml.safe_load((self.project_path / "configs" / "providers.yaml").read_text(encoding="utf-8")) or {}
        return data.get("providers", {}).get(provider, {}).get("models", {}).get(role) or self.providers[provider].model

    def _load_canon(self) -> Dict[str, Any]:
        path = self.project_path / "canon.yaml"
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def _ensure_seed_facts(self):
        # Seed hard state from canon
        for rule in self.canon.get("HARD_RULE", []):
            if rule.get("key") == "system.warehouse.accessible":
                existing = self.fact_store.query_facts(0, {"subject": "system.warehouse", "predicate": "accessible"})
                if not existing:
                    self.fact_store.upsert_facts(
                        0,
                        [
                            Fact(
                                subject="system.warehouse",
                                predicate="accessible",
                                object_value=rule.get("value", False),
                                valid_from_chapter=0,
                                source_chapter=0,
                                hard_flag=True,
                            )
                        ],
                    )
        # Seed protagonist aliases
        for fact in self.canon.get("SOFT_FACT", []):
            if fact.get("key") == "protagonist.canonical_name":
                self.fact_store.upsert_entity(fact.get("value"), "character", [])
            if fact.get("key") == "protagonist.aliases":
                canonical = self._canon_value("protagonist.canonical_name")
                if canonical:
                    self.fact_store.upsert_entity(canonical, "character", fact.get("value", []))

    def _canon_value(self, key: str):
        for fact in self.canon.get("SOFT_FACT", []):
            if fact.get("key") == key:
                return fact.get("value")
        return None

    def run(self, chapter_num: int):
        title, summary = get_chapter_info(chapter_num)
        chapter_dir = self.pipeline_root / f"c{chapter_num:03d}"
        chapter_dir.mkdir(parents=True, exist_ok=True)

        outline = self._load_or_generate_outline(chapter_num, title, summary)
        snapshot = self.fact_store.get_snapshot(chapter_num - 1)
        snapshot_path = chapter_dir / f"state_snapshot_{chapter_num:03d}.json"
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

        context = self._build_context(chapter_num, outline, snapshot)
        draft = self._write_draft(chapter_num, title, outline, context, chapter_dir)
        (chapter_dir / "draft.txt").write_text(draft, encoding="utf-8")

        issues = self._review(chapter_num, chapter_dir, draft, snapshot, context)
        if self._has_blocker(issues):
            revised = self._revise(chapter_num, draft, issues, context, chapter_dir)
            (chapter_dir / "revised.txt").write_text(revised, encoding="utf-8")
            issues = self._review(chapter_num, chapter_dir, revised, snapshot, context, suffix="revise")
            if self._has_blocker(issues):
                strict = self._revise_strict(chapter_num, revised, issues, context, chapter_dir, snapshot)
                (chapter_dir / "revised_strict.txt").write_text(strict, encoding="utf-8")
                issues = self._review(chapter_num, chapter_dir, strict, snapshot, context, suffix="revise2")
                if self._has_blocker(issues):
                    return False
                draft = strict
            else:
                draft = revised

        final_text, state_diff = self._extract_final(draft)
        if not state_diff:
            state_diff = {"facts": [], "rename_events": []}
            (chapter_dir / "state_diff_missing.json").write_text(
                json.dumps({"warning": "missing_state_diff"}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        (chapter_dir / "final.txt").write_text(final_text, encoding="utf-8")
        (chapter_dir / "state_diff.json").write_text(
            json.dumps(state_diff, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        self._commit(chapter_num, title, final_text, state_diff, chapter_dir)
        self._save_chapter_file(chapter_num, title, final_text)
        return True

    def _load_or_generate_outline(self, chapter_num: int, title: str, summary: str) -> str:
        path = self.project_path / "outline" / "L3-chapters" / f"v01-c{chapter_num:03d}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        prompt = f"""你是小说策划编辑，请为第{chapter_num}章生成简洁章纲。
标题：{title}
内容：{summary}
输出结构：场景列表 + 每场景目标。
"""
        outline_dir = self.pipeline_root / f"c{chapter_num:03d}"
        outline_dir.mkdir(parents=True, exist_ok=True)
        self._save_prompt(outline_dir / "prompt_outline.txt", "你是专业网络小说策划编辑。", prompt)
        raw = self.writer_client.chat(
            [
                {"role": "system", "content": "你是专业网络小说策划编辑。"},
                {"role": "user", "content": prompt},
            ]
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw, encoding="utf-8")
        return raw

    def _build_context(self, chapter_num: int, outline: str, snapshot: Dict[str, Any]) -> str:
        hard_state = json.dumps(snapshot, ensure_ascii=False, indent=2)
        core = self.memory_bank.read_core()
        memory_bank_excerpt = "\n".join(
            [core.get("world_and_characters.md", ""), core.get("activeContext.md", "")]
        )[:2000]
        recall = ""
        if self.memory_adapter is not None:
            recall = self.memory_adapter.query_context(
                f"第{chapter_num-1}章到第{chapter_num}章之前发生的重要事件"
            )

        context = (
            "# HardState Snapshot\n"
            + hard_state
            + "\n\n# MemoryBank Excerpt\n"
            + memory_bank_excerpt
            + "\n\n# SimpleMem Recall\n"
            + (recall or "（无）")
            + "\n\n# Outline\n"
            + outline
        )
        return context

    def _write_draft(self, chapter_num: int, title: str, outline: str, context: str, chapter_dir: Path) -> str:
        prompt = f"""你是网络小说写手，请写第{chapter_num}章正文。

## Context
{context}

## Requirements
- 只输出正文 + 末尾 State Diff
- State Diff 用 JSON 包裹在 ```json 代码块中，字段示例：
{{"facts": [{{"subject": "system.warehouse", "predicate": "accessible", "value": true, "hard": true, "reason": "解锁"}}], "rename_events": [{{"canonical_name": "艾伦·诺斯", "new_name": "林远", "reason": "前世身份揭示"}}]}}
- 不得出现与 HardState 冲突内容；若需改变必须在剧情中解释
- 叙述中使用 canonical_name，别名仅作为对白/绰号出现，且如需更名必须在 State Diff 中登记
- 禁止条目式优缺点分析
- 禁止出现“场景安排/写作要点/本章目的/基本信息”等提纲或说明性内容
- 禁止 Markdown 标题/小节标题（如 #、##、### 或“场景一/二”），必须是连续叙事正文
- 所有数值/资源/进度必须与 HardState 一致，如需变化需在剧情中解释并在 State Diff 中说明

## Title
{title}
"""
        self._save_prompt(chapter_dir / "prompt_draft.txt", "你是顶级西幻种田网文写手。", prompt)
        return self.writer_client.chat(
            [
                {"role": "system", "content": "你是顶级西幻种田网文写手。"},
                {"role": "user", "content": prompt},
            ]
        )

    def _review(
        self,
        chapter_num: int,
        chapter_dir: Path,
        draft: str,
        snapshot: Dict[str, Any],
        context: str,
        suffix: str = "draft",
    ) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        review_text, _ = self._extract_final(draft)
        if self.config.use_hard_checker:
            hard_issues = check_hard_state(review_text, snapshot, self.canon)
            issues.extend(hard_issues)

        if self.config.use_consistency_checker:
            state_snapshot = self._snapshot_for_state_manager(snapshot)
            checker = run_consistency_check(state_snapshot, {}, review_text)
            for issue in checker.get("issues", []):
                severity = "minor"
                if issue.get("severity") == "error":
                    severity = "blocker"
                issues.append(
                    {
                        "type": "state_violation",
                        "severity": severity,
                        "evidence": [{"quote": issue.get("evidence_new") or "", "chapter_pos": "unknown"}],
                        "related_memory_keys": [issue.get("rule_id", "")],
                        "fix_suggestion": "补充剧情解释或改写相关段落。",
                        "requires_rewrite_scope": "paragraph",
                    }
                )

        if self.critic_configs:
            critic_results = run_critics(
                review_text,
                canon_summary=json.dumps(self.canon, ensure_ascii=False),
                state_snapshot=snapshot,
                context_excerpt=context[:1200],
                critic_configs=self.critic_configs,
                max_workers=self.config.critics_workers,
                output_dir=chapter_dir,
            )
            issues_by_provider = {r.provider: r.issues for r in critic_results}
            merge_result = merge_issues(issues_by_provider, arbiter=self._arbitrate_issue)
            write_merge_outputs(merge_result, chapter_dir)
            issues.extend(merge_result.merged)

        if not issues and self._looks_like_outline(review_text):
            issues.append(
                {
                    "type": "style_meta",
                    "severity": "major",
                    "evidence": [{"quote": "文本呈提纲/说明结构", "chapter_pos": "unknown"}],
                    "related_memory_keys": [],
                    "fix_suggestion": "改为连续叙事正文，去掉标题/清单/说明。",
                    "requires_rewrite_scope": "scene",
                }
            )

        # write merged issues file for this stage
        (chapter_dir / f"issues_{suffix}.json").write_text(
            json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return issues

    def _revise(self, chapter_num: int, draft: str, issues: List[Dict[str, Any]], context: str, chapter_dir: Path) -> str:
        prompt = f"""请根据 issues 最小化修订正文，不要重写整章。

## Context
{context}

## Issues
{json.dumps(issues, ensure_ascii=False, indent=2)}

输出修订后的正文 + 末尾 State Diff JSON 代码块。
若问题涉及标题/提纲/清单等非叙事结构，必须彻底删除对应内容，改为连续叙事。
修订后正文不得包含编号列表或项目符号清单。
若涉及数值冲突（如星尘/资源/等级），必须改为与 HardState 一致，或补充消耗/获取桥段并在 State Diff 标注。
"""
        self._save_prompt(chapter_dir / "prompt_revise.txt", "你是小说修订编辑，只做最小修改。", prompt)
        return self.writer_client.chat(
            [
                {"role": "system", "content": "你是小说修订编辑，只做最小修改。"},
                {"role": "user", "content": prompt},
            ]
        )

    def _revise_strict(
        self,
        chapter_num: int,
        draft: str,
        issues: List[Dict[str, Any]],
        context: str,
        chapter_dir: Path,
        snapshot: Dict[str, Any],
    ) -> str:
        overrides = self._extract_numeric_overrides(issues, snapshot)
        decision = snapshot.get("艾伦·诺斯", {}).get("decision_made")
        extra = ""
        if overrides:
            extra = "必须按以下数值修正：\n" + "\n".join(f"- {item}" for item in overrides) + "\n"
        if decision:
            extra += f"HardState 已记录 decision_made={decision}，正文不得再描写决策过程，只能写执行与准备。\n"

        prompt = f"""这是严格修订。必须逐条解决 issues，不得保留任何被指出的问题。

## Context
{context}

## Issues
{json.dumps(issues, ensure_ascii=False, indent=2)}

输出修订后的正文 + 末尾 State Diff JSON 代码块。
若涉及仓库不可用，严禁出现“从系统仓库取出”等行为，改为现实来源或系统直接发放。
禁止任何 Markdown 标题或清单。
{extra}
"""
        self._save_prompt(chapter_dir / "prompt_revise_strict.txt", "你是严格修订编辑，必须解决问题。", prompt)
        return self.writer_client.chat(
            [
                {"role": "system", "content": "你是严格修订编辑，必须解决问题。"},
                {"role": "user", "content": prompt},
            ]
        )

    def _arbitrate_issue(self, issues: List[Dict[str, Any]]) -> (Dict[str, Any], str):
        prompt = f"""以下是同一问题的不同审稿建议，请选择最可执行的一条，并说明原因。

Issues:
{json.dumps(issues, ensure_ascii=False, indent=2)[:3000]}

输出 JSON：{{"issue": {{...}}, "reason": "..."}}。"""
        try:
            raw = self.writer_client.chat(
                [
                    {"role": "system", "content": "你是审稿裁判，只做选择，不做改写。"},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            data = safe_json_loads(raw)
            chosen = data.get("issue") or issues[0]
            reason = data.get("reason", "arbiter_selected")
            return chosen, reason
        except Exception:
            return issues[0], "arbiter_failed_fallback"

    def _snapshot_for_state_manager(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        state: Dict[str, Any] = {"system": {"warehouse": {}}}
        entries = []
        warehouse = snapshot.get("system.warehouse", {})
        if "accessible" in warehouse:
            state["system"]["warehouse"]["accessible"] = warehouse["accessible"]
            entries.append(
                {
                    "path": "system.warehouse.accessible",
                    "value": warehouse["accessible"],
                    "evidence": "temporal_fact_store",
                }
            )
        return {"state": state, "entries": entries}

    def _extract_final(self, draft: str) -> (str, Dict[str, Any]):
        state_diff = {}
        match = re.search(r"```json\s*([\s\S]*?)\s*```", draft)
        if match:
            try:
                state_diff = safe_json_loads(match.group(0))
            except Exception:
                state_diff = {}
            final_text = draft[: match.start()].strip()
        else:
            final_text = draft.strip()
        return final_text, state_diff

    def _commit(
        self,
        chapter_num: int,
        title: str,
        final_text: str,
        state_diff: Dict[str, Any],
        chapter_dir: Path,
    ):
        chapter_hash = hashlib.sha256(final_text.encode("utf-8")).hexdigest()[:12]
        (chapter_dir / "chapter_hash.txt").write_text(chapter_hash, encoding="utf-8")

        # apply facts
        facts = []
        for item in state_diff.get("facts", []):
            facts.append(
                Fact(
                    subject=item.get("subject"),
                    predicate=item.get("predicate"),
                    object_value=item.get("value"),
                    qualifiers={"reason": item.get("reason")},
                    valid_from_chapter=chapter_num,
                    source_chapter=chapter_num,
                    hard_flag=bool(item.get("hard", True)),
                )
            )
        if facts:
            self.fact_store.upsert_facts(chapter_num, facts)

        for event in state_diff.get("rename_events", []):
            canonical = event.get("canonical_name") or self._canon_value("protagonist.canonical_name")
            new_name = event.get("new_name")
            if canonical and new_name:
                self.fact_store.add_rename_event(canonical, chapter_num, new_name, event.get("reason", ""))

        # memory bank update
        proposal, applied = self.memory_bank.update_from_chapter(chapter_num, final_text, client=None)
        proposal_path = chapter_dir / "memory_patch_proposal.json"
        proposal_path.write_text(json.dumps({"ops": proposal.ops}, ensure_ascii=False, indent=2), encoding="utf-8")
        applied_path = chapter_dir / "memory_patch_applied.json"
        applied_path.write_text(json.dumps({"ops": applied.ops}, ensure_ascii=False, indent=2), encoding="utf-8")

        # memory index
        index_path = self.memory_commits / "memory_index.json"
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
        previous = index.get(str(chapter_num))
        index[str(chapter_num)] = chapter_hash
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

        commit_file = self.memory_commits / f"Chapter_{chapter_num:03d}_{chapter_hash}.json"
        commit_payload = {
            "chapter": chapter_num,
            "hash": chapter_hash,
            "replaced": previous,
            "state_diff": state_diff,
            "active": True,
        }
        commit_file.write_text(json.dumps(commit_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        if previous:
            previous_path = self.memory_commits / f"Chapter_{chapter_num:03d}_{previous}.json"
            if previous_path.exists():
                previous_payload = json.loads(previous_path.read_text(encoding="utf-8"))
                previous_payload["replaced_by"] = chapter_hash
                previous_payload["active"] = False
                previous_path.write_text(
                    json.dumps(previous_payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )

        if self.memory_adapter is not None:
            self.memory_adapter.add_chapter(chapter_num=chapter_num, content=final_text, title=title)

    def _save_chapter_file(self, chapter_num: int, title: str, final_text: str):
        chapter_dir = self.project_path / "chapters" / "v01"
        chapter_dir.mkdir(parents=True, exist_ok=True)
        safe_title = title.replace(":", "：").replace("/", "_").replace("\\", "_")
        safe_title = safe_title.replace("?", "？").replace("*", "_").replace('"', "'")
        path = chapter_dir / f"第{chapter_num}章_{safe_title}.txt"
        cleaned = self._strip_leading_headings(final_text)
        path.write_text(f"第{chapter_num}章 {title}\n\n" + cleaned, encoding="utf-8")

    def _has_blocker(self, issues: List[Dict[str, Any]]) -> bool:
        for issue in issues:
            if issue.get("severity") in {"blocker", "major"}:
                return True
        return False

    def _format_for_reading(self, text: str) -> str:
        paragraphs: List[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                paragraphs.append("")
                continue
            if line.startswith("#"):
                continue
            if re.match(r"^场景\\s*\\d+", line) or line.startswith("场景"):
                continue
            for seg in self._split_dialogue(line):
                paragraphs.append(seg)

        formatted: List[str] = []
        for para in paragraphs:
            if not para:
                if formatted and formatted[-1] != "":
                    formatted.append("")
                continue
            formatted.append("　　" + para)

        return "\n".join(formatted).strip()

    def _split_dialogue(self, line: str) -> List[str]:
        if "“" not in line and "”" not in line:
            return [line]

        segments: List[str] = []
        buffer = ""
        in_quote = False

        for ch in line:
            if ch == "“":
                if buffer.strip():
                    segments.append(buffer.strip())
                buffer = "“"
                in_quote = True
                continue
            buffer += ch
            if ch == "”" and in_quote:
                segments.append(buffer.strip())
                buffer = ""
                in_quote = False

        if buffer.strip():
            segments.append(buffer.strip())

        return segments

    def _strip_leading_headings(self, text: str) -> str:
        lines = text.splitlines()
        while lines and lines[0].lstrip().startswith("#"):
            lines.pop(0)
        return "\n".join(lines).lstrip()

    def _extract_numeric_overrides(self, issues: List[Dict[str, Any]], snapshot: Dict[str, Any]) -> List[str]:
        import re

        overrides: List[str] = []
        # Use hard snapshot if available
        star_dust = snapshot.get("艾伦·诺斯", {}).get("star_dust")
        for issue in issues:
            blob = f"{issue.get('description','')} {issue.get('fix_suggestion','')}"
            if "星尘" in blob:
                if star_dust is not None:
                    overrides.append(f"星尘数值必须为 {star_dust}")
                else:
                    nums = [int(n) for n in re.findall(r"\d+", blob)]
                    if nums:
                        overrides.append(f"星尘数值必须为 {max(nums)}")
                overrides.append("星尘对应抽奖次数=星尘/20，若出现次数描述必须一致")
        return overrides

    def _looks_like_outline(self, text: str) -> bool:
        markers = [
            "本章目的",
            "写作要点",
            "场景安排",
            "基本信息",
            "注意事项",
        ]
        if any(m in text for m in markers):
            return True
        if "\n- " in text or "\n* " in text:
            return True
        if "[ ]" in text or "[x]" in text:
            return True
        return False

    def _save_prompt(self, path: Path, system_prompt: str, user_prompt: str):
        payload = f"SYSTEM:\\n{system_prompt}\\n\\nUSER:\\n{user_prompt}\\n"
        path.write_text(payload, encoding="utf-8")

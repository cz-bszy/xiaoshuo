"""
故事状态管理系统（硬状态 + 软状态）
负责：硬状态快照/校验/提交，软状态（叙事状态）更新与一致性检查
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None


WAREHOUSE_KEYWORDS = [
    "系统仓库",
    "仓库界面",
    "库存",
    "物品栏",
    "储物",
    "存入",
    "取出",
    "打开仓库",
    "仓库",
]
WAREHOUSE_EXCLUDE = [
    "家族仓库",
    "粮仓",
    "仓库钥匙",
    "仓库账目",
]
WAREHOUSE_SUCCESS = [
    "成功",
    "终于",
    "顺利",
    "弹出界面",
    "列表",
    "显示",
    "取出了",
    "拿出",
    "收入",
    "放入",
    "存入成功",
]
WAREHOUSE_FAILURE = [
    "打不开",
    "无法打开",
    "没有反应",
    "提示权限不足",
    "权限不足",
    "未解锁",
    "未开启",
    "失败",
    "被拒绝",
]
WAREHOUSE_UNLOCK = [
    "解锁",
    "权限开通",
    "获得权限",
    "权限通过",
    "系统提示",
    "功能开启",
    "开放仓库",
]


@dataclass
class Issue:
    severity: str
    rule_id: str
    message: str
    evidence_new: Optional[str] = None
    evidence_old: Optional[str] = None
    suggestions: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "rule_id": self.rule_id,
            "message": self.message,
            "evidence_new": self.evidence_new,
            "evidence_old": self.evidence_old,
            "suggestions": self.suggestions,
        }


def _has_error(issues: List[Dict[str, Any] | Issue]) -> bool:
    for issue in issues:
        if isinstance(issue, Issue):
            severity = issue.severity
        else:
            severity = issue.get("severity")
        if severity == "error":
            return True
    return False


def _split_sentences(text: str) -> List[str]:
    # 简单中文分句
    parts = re.split(r"(?<=[。！？!?])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def _first_sentence_with_keywords(text: str, keywords: List[str]) -> Optional[str]:
    for sentence in _split_sentences(text):
        if any(k in sentence for k in keywords):
            return sentence
    return None


def _detect_warehouse_signals(text: str) -> Dict[str, Any]:
    if any(k in text for k in WAREHOUSE_EXCLUDE):
        return {"trigger": False, "success": False, "failure": False, "unlock": False, "evidence": None}

    trigger = any(k in text for k in WAREHOUSE_KEYWORDS)
    if not trigger:
        return {"trigger": False, "success": False, "failure": False, "unlock": False, "evidence": None}

    evidence = _first_sentence_with_keywords(text, WAREHOUSE_KEYWORDS)
    sentences = _split_sentences(text)

    def sentence_has(sentence: str, keywords: List[str]) -> bool:
        return any(k in sentence for k in keywords)

    success = False
    failure = False
    unlock = False

    for sentence in sentences:
        if not sentence_has(sentence, WAREHOUSE_KEYWORDS):
            continue
        if sentence_has(sentence, WAREHOUSE_SUCCESS):
            success = True
            evidence = sentence
        if sentence_has(sentence, WAREHOUSE_FAILURE):
            failure = True
            if evidence is None:
                evidence = sentence
        if sentence_has(sentence, WAREHOUSE_UNLOCK):
            unlock = True
            if evidence is None:
                evidence = sentence

    return {
        "trigger": True,
        "success": success,
        "failure": failure,
        "unlock": unlock,
        "evidence": evidence,
    }


def _issue(
    severity: str,
    rule_id: str,
    message: str,
    evidence_new: Optional[str] = None,
    evidence_old: Optional[str] = None,
    suggestions: Optional[List[Dict[str, str]]] = None,
) -> Issue:
    return Issue(
        severity=severity,
        rule_id=rule_id,
        message=message,
        evidence_new=evidence_new,
        evidence_old=evidence_old,
        suggestions=suggestions or [],
    )


def _flatten_state_entries(data: Any, base_path: str = "", meta: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    meta = meta or {}

    if isinstance(data, dict):
        local_meta = dict(meta)
        if "evidence" in data:
            local_meta["evidence"] = data.get("evidence")
        if "strict" in data:
            local_meta["strict"] = data.get("strict")
        if "last_update_chapter" in data:
            local_meta["last_update_chapter"] = data.get("last_update_chapter")

        for key, value in data.items():
            if key in {"evidence", "strict", "last_update_chapter"}:
                continue
            path = f"{base_path}.{key}" if base_path else key
            if isinstance(value, dict):
                if "value" in value:
                    entries.append(
                        {
                            "path": path,
                            "value": value.get("value"),
                            "valid_from": value.get("valid_from", 0),
                            "valid_to": value.get("valid_to"),
                            "evidence": value.get("evidence", local_meta.get("evidence")),
                            "source_chapter": value.get("source_chapter", local_meta.get("last_update_chapter", 0)),
                            "strict": value.get("strict", local_meta.get("strict", True)),
                            "cause": value.get("cause"),
                        }
                    )
                else:
                    entries.extend(_flatten_state_entries(value, path, local_meta))
            else:
                strict_default = local_meta.get("strict", True)
                if key in {"unlocked_by", "last_update_chapter"}:
                    strict_default = False
                entries.append(
                    {
                        "path": path,
                        "value": value,
                        "valid_from": local_meta.get("last_update_chapter", 0),
                        "valid_to": None,
                        "evidence": local_meta.get("evidence"),
                        "source_chapter": local_meta.get("last_update_chapter", 0),
                        "strict": strict_default,
                        "cause": None,
                    }
                )

    return entries


def _build_nested_state(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    state: Dict[str, Any] = {}
    for entry in entries:
        path = entry.get("path")
        if not path:
            continue
        parts = path.split(".")
        cursor = state
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = entry.get("value")
    return state


class StoryStateManager:
    """权威状态管理器（硬状态 + 软状态）"""

    def __init__(self, project_path: Optional[Path] = None):
        self.project_path = project_path or Path(__file__).resolve().parent
        self.repo_root = self.project_path.parents[1]

        self.state_dir = self.project_path / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.snapshot_path = self.state_dir / "state_snapshot.json"
        self.events_path = self.state_dir / "state_events.jsonl"
        self.invariants_path = self.project_path / "worldbook" / "invariants.yaml"
        self.system_state_path = self.project_path / "worldbook" / "system_state.yaml"

        self.story_state_path = self.project_path / "worldbook" / "dynamic" / "story_state.json"

        self._lock = threading.Lock()
        self._snapshot_entries: List[Dict[str, Any]] = []
        self._snapshot_index: Dict[str, Dict[str, Any]] = {}
        self._last_committed_chapter = 0

        self.invariants = self._load_invariants()
        self.load()

        self.story_state = self._load_story_state()
        self._llm_client = self._init_llm_client()

    # -------------------------
    # 硬状态：加载 / 快照 / 校验
    # -------------------------
    def _load_invariants(self) -> List[Dict[str, Any]]:
        if not self.invariants_path.exists():
            return []
        with open(self.invariants_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("invariants", []) if isinstance(data, dict) else []

    def _load_system_state_entries(self) -> List[Dict[str, Any]]:
        if not self.system_state_path.exists():
            return []
        with open(self.system_state_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return _flatten_state_entries(data)

    def _load_snapshot_file(self) -> bool:
        if not self.snapshot_path.exists():
            return False
        with open(self.snapshot_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._snapshot_entries = data.get("entries", [])
        self._snapshot_index = {entry["path"]: entry for entry in self._snapshot_entries if "path" in entry}
        self._last_committed_chapter = data.get("last_chapter", 0)
        return True

    def _replay_events(self):
        entries: List[Dict[str, Any]] = []
        index: Dict[str, Dict[str, Any]] = {}
        last_chapter = 0
        if not self.events_path.exists():
            return entries, index, last_chapter

        with open(self.events_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                event = json.loads(line)
                chapter_num = int(event.get("chapter", 0))
                last_chapter = max(last_chapter, chapter_num)
                for update in event.get("updates", []):
                    self._apply_update_entry(update, chapter_num, entries, index)

        return entries, index, last_chapter

    def _apply_update_entry(
        self,
        update: Dict[str, Any],
        chapter_num: int,
        entries: List[Dict[str, Any]],
        index: Dict[str, Dict[str, Any]],
    ):
        path = update.get("path")
        if not path:
            return
        existing = index.get(path)
        if existing:
            existing["valid_to"] = chapter_num - 1

        new_entry = {
            "path": path,
            "value": update.get("value"),
            "valid_from": update.get("valid_from", chapter_num),
            "valid_to": update.get("valid_to"),
            "evidence": update.get("evidence"),
            "source_chapter": update.get("source_chapter", chapter_num),
            "strict": update.get("strict", True),
            "cause": update.get("cause"),
        }
        entries.append(new_entry)
        index[path] = new_entry

    def load(self):
        """读取 snapshot 或 events，并叠加 system_state.yaml"""
        loaded = self._load_snapshot_file()
        if not loaded:
            entries, index, last_chapter = self._replay_events()
            self._snapshot_entries = entries
            self._snapshot_index = index
            self._last_committed_chapter = last_chapter

        system_entries = self._load_system_state_entries()
        for entry in system_entries:
            path = entry.get("path")
            if not path:
                continue
            existing = self._snapshot_index.get(path)
            if existing is None or existing.get("source_chapter", 0) == 0:
                self._snapshot_entries.append(entry)
                self._snapshot_index[path] = entry

        self._persist_snapshot()

    def _persist_snapshot(self):
        payload = {
            "last_chapter": self._last_committed_chapter,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "entries": self._snapshot_entries,
        }
        with open(self.snapshot_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def get_snapshot(self, chapter_num: int, topic_keywords: Optional[List[str]] = None) -> Dict[str, Any]:
        """返回写作前快照（默认取 chapter_num-1 生效的状态）"""
        effective_chapter = max(chapter_num - 1, 0)
        active_entries = [
            entry
            for entry in self._snapshot_entries
            if entry.get("valid_from", 0) <= effective_chapter
            and (entry.get("valid_to") is None or entry.get("valid_to") >= effective_chapter)
        ]

        filtered_entries = self._filter_entries_by_topics(active_entries, topic_keywords)
        state = _build_nested_state(filtered_entries)
        invariants = self._select_invariants(topic_keywords)

        return {
            "chapter_num": chapter_num,
            "effective_chapter": effective_chapter,
            "state": state,
            "entries": filtered_entries,
            "invariants": invariants,
        }

    def _filter_entries_by_topics(
        self,
        entries: List[Dict[str, Any]],
        topic_keywords: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        if not topic_keywords:
            return [entry for entry in entries if entry.get("strict", False)] + [
                entry for entry in entries if not entry.get("strict", False)
            ]

        lowered = [k.lower() for k in topic_keywords]
        result = []
        for entry in entries:
            path = entry.get("path", "")
            if entry.get("strict"):
                result.append(entry)
                continue
            if any(k in path.lower() for k in lowered):
                result.append(entry)
        return result

    def _select_invariants(self, topic_keywords: Optional[List[str]]) -> List[Dict[str, Any]]:
        if not topic_keywords:
            return self.invariants
        lowered = [k.lower() for k in topic_keywords]
        matched = []
        for inv in self.invariants:
            scope = [s.lower() for s in inv.get("scope_keywords", [])]
            if any(k in scope for k in lowered):
                matched.append(inv)
        return matched

    @staticmethod
    def format_snapshot_for_prompt(snapshot: Dict[str, Any]) -> str:
        return yaml.safe_dump(snapshot.get("state", {}), allow_unicode=True, sort_keys=False)

    @staticmethod
    def format_invariants_for_prompt(invariants: List[Dict[str, Any]]) -> str:
        if not invariants:
            return "(无)"
        lines = []
        for inv in invariants:
            lines.append(
                f"- {inv.get('id')}: {inv.get('description')} (severity={inv.get('severity', 'warn')})"
            )
        return "\n".join(lines)

    def validate_plan(self, plan: Dict[str, Any], snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        issues: List[Issue] = []
        state = snapshot.get("state", {})
        accessible = (
            state.get("system", {})
            .get("warehouse", {})
            .get("accessible", False)
        )
        entry_old = self._get_entry_from_snapshot(snapshot, "system.warehouse.accessible")

        plan_has_warehouse = self._plan_has_warehouse_action(plan)
        plan_unlocks = self._plan_unlocks_warehouse(plan)
        plan_failure = self._plan_has_warehouse_failure(plan)

        if plan_has_warehouse and not accessible:
            if plan_failure:
                issues.append(
                    _issue(
                        "warn",
                        "system.warehouse.access_failed",
                        "计划中包含仓库访问失败描写，仓库仍不可用。",
                        evidence_old=entry_old.get("evidence") if entry_old else None,
                    )
                )
            elif not plan_unlocks["has_unlock"]:
                issues.append(
                    _issue(
                        "error",
                        "system.warehouse.strict_access",
                        "计划中包含仓库访问，但当前仓库不可用且未包含解锁事件。",
                        evidence_old=entry_old.get("evidence") if entry_old else None,
                        suggestions=[
                            {
                                "type": "add_unlock_event",
                                "hint": "在计划中加入解锁/权限获得事件，并在后续才能访问仓库。",
                            },
                            {
                                "type": "remove_warehouse_action",
                                "hint": "删除或改写仓库访问行为。",
                            },
                        ],
                    )
                )
            elif not plan_unlocks["has_cause"]:
                issues.append(
                    _issue(
                        "error",
                        "system.warehouse.unlock_without_cause",
                        "计划声明解锁仓库，但缺少明确触发原因。",
                        evidence_old=entry_old.get("evidence") if entry_old else None,
                        suggestions=[
                            {
                                "type": "add_unlock_cause",
                                "hint": "补充任务完成/系统提示/权限获得等因果桥段。",
                            }
                        ],
                    )
                )

        return [issue.to_dict() for issue in issues]

    def _plan_has_warehouse_action(self, plan: Dict[str, Any]) -> bool:
        if not isinstance(plan, dict):
            return False
        actions = plan.get("actions", [])
        for action in actions:
            if not isinstance(action, dict):
                continue
            action_type = str(action.get("type", ""))
            if "warehouse" in action_type or "仓库" in action_type:
                return True
            serialized = json.dumps(action, ensure_ascii=False)
            if any(k in serialized for k in WAREHOUSE_KEYWORDS):
                return True
        serialized_plan = json.dumps(plan, ensure_ascii=False)
        return any(k in serialized_plan for k in WAREHOUSE_KEYWORDS)

    def _plan_unlocks_warehouse(self, plan: Dict[str, Any]) -> Dict[str, bool]:
        if not isinstance(plan, dict):
            return {"has_unlock": False, "has_cause": False}
        state_changes = plan.get("state_changes", [])
        for change in state_changes:
            if not isinstance(change, dict):
                continue
            path = change.get("path")
            to_value = change.get("to", change.get("value"))
            if path == "system.warehouse.accessible" and to_value is True:
                cause = change.get("cause_event") or change.get("cause")
                return {"has_unlock": True, "has_cause": bool(cause and str(cause).strip())}
        return {"has_unlock": False, "has_cause": False}

    def _plan_has_warehouse_failure(self, plan: Dict[str, Any]) -> bool:
        if not isinstance(plan, dict):
            return False
        serialized = json.dumps(plan, ensure_ascii=False)
        return any(k in serialized for k in WAREHOUSE_FAILURE)

    def validate_chapter(self, chapter_text: str, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        issues: List[Issue] = []
        state = snapshot.get("state", {})
        accessible = (
            state.get("system", {})
            .get("warehouse", {})
            .get("accessible", False)
        )
        entry_old = self._get_entry_from_snapshot(snapshot, "system.warehouse.accessible")

        signals = _detect_warehouse_signals(chapter_text)
        if signals.get("trigger"):
            if signals.get("success") and not accessible:
                if signals.get("unlock"):
                    issues.append(
                        _issue(
                            "warn",
                            "system.warehouse.unlocked_in_chapter",
                            "本章出现仓库成功访问，但仓库原本不可用；已检测到解锁桥段，请确保状态更新。",
                            evidence_new=signals.get("evidence"),
                            evidence_old=entry_old.get("evidence") if entry_old else None,
                        )
                    )
                else:
                    issues.append(
                        _issue(
                            "error",
                            "system.warehouse.strict_access",
                            "仓库不可用，但正文出现成功访问/取物等行为。",
                            evidence_new=signals.get("evidence"),
                            evidence_old=entry_old.get("evidence") if entry_old else None,
                            suggestions=[
                                {
                                    "type": "rewrite_to_fail_access",
                                    "hint": "将成功访问改写为尝试失败/权限不足。",
                                },
                                {
                                    "type": "add_unlock_event",
                                    "hint": "插入解锁/权限获得桥段，再进行访问。",
                                },
                            ],
                        )
                    )
            elif signals.get("failure") and not accessible:
                issues.append(
                    _issue(
                        "warn",
                        "system.warehouse.access_failed",
                        "仓库不可用且正文出现访问失败描写，保持一致。",
                        evidence_new=signals.get("evidence"),
                        evidence_old=entry_old.get("evidence") if entry_old else None,
                    )
                )

        return [issue.to_dict() for issue in issues]

    def extract_state_updates(self, chapter_text: str, chapter_num: int) -> List[Dict[str, Any]]:
        """抽取硬状态变更（最小版本：仓库解锁）"""
        updates: List[Dict[str, Any]] = []

        signals = _detect_warehouse_signals(chapter_text)
        if signals.get("trigger") and signals.get("unlock"):
            updates.append(
                {
                    "path": "system.warehouse.accessible",
                    "value": True,
                    "valid_from": chapter_num,
                    "valid_to": None,
                    "evidence": signals.get("evidence") or "本章解锁仓库",
                    "source_chapter": chapter_num,
                    "strict": True,
                    "cause": "chapter_unlock",
                }
            )

        # 可选 LLM 抽取（暂未启用）
        return updates

    def _get_entry_from_snapshot(self, snapshot: Dict[str, Any], path: str) -> Optional[Dict[str, Any]]:
        for entry in snapshot.get("entries", []):
            if entry.get("path") == path:
                return entry
        return None

    def commit(
        self,
        chapter_num: int,
        updates: List[Dict[str, Any]],
        issues: List[Dict[str, Any]],
        persist: bool = True,
    ):
        if _has_error(issues):
            raise RuntimeError("存在 error 级别问题，禁止提交状态。")
        with self._lock:
            if chapter_num <= self._last_committed_chapter:
                raise RuntimeError(
                    f"章节提交顺序错误：当前 {chapter_num}，已提交 {self._last_committed_chapter}"
                )

            event = {
                "chapter": chapter_num,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "updates": updates,
                "issues": issues,
            }
            if persist:
                with open(self.events_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")

            for update in updates:
                self._apply_update_entry(update, chapter_num, self._snapshot_entries, self._snapshot_index)

            self._last_committed_chapter = chapter_num
            if persist:
                self._persist_snapshot()

                diff_path = self.state_dir / "diffs"
                diff_path.mkdir(parents=True, exist_ok=True)
                diff_file = diff_path / f"c{chapter_num:03d}.json"
                with open(diff_file, "w", encoding="utf-8") as f:
                    json.dump({"chapter": chapter_num, "updates": updates}, f, ensure_ascii=False, indent=2)

    # -------------------------
    # 软状态（原有故事状态）
    # -------------------------
    def _load_story_state(self) -> Dict[str, Any]:
        if self.story_state_path.exists():
            with open(self.story_state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_story_state(self):
        if not self.story_state:
            return
        self.story_state.setdefault("meta", {})["last_updated"] = datetime.now().strftime("%Y-%m-%d")
        with open(self.story_state_path, "w", encoding="utf-8") as f:
            json.dump(self.story_state, f, ensure_ascii=False, indent=2)

    def generate_context_for_writing(
        self,
        chapter_num: int,
        topics: Optional[List[str]] = None,
        use_semantic_memory: bool = True,
    ) -> str:
        """生成软状态上下文（供写作参考）"""
        state = self.story_state
        if not state:
            return ""

        context = f"""## 当前故事状态（第{chapter_num}章写作用）

### 时间
- 故事时间：{state.get('meta', {}).get('story_time', '未知')}
- 当前章节：第{chapter_num}章

### 主角状态
- 姓名：{state.get('protagonist', {}).get('name', '艾伦·诺斯')}
- 境界：{state.get('protagonist', {}).get('realm', {}).get('current', '未知')} ({state.get('protagonist', {}).get('realm', {}).get('level', '')})
- 位置：{state.get('protagonist', {}).get('location', '未知')}
- 技能：{', '.join([s['name'] for s in state.get('protagonist', {}).get('skills', [])])}

### 领地状态
- 人口：{state.get('territory', {}).get('population', 0)}人
- 设施：{', '.join([f['name'] for f in state.get('territory', {}).get('facilities', [])])}
- 军事：巡逻队{state.get('territory', {}).get('military', {}).get('patrol_team', 0)}人，民兵{state.get('territory', {}).get('military', {}).get('militia', 0)}人

### 关键角色
"""
        for name, info in state.get("characters", {}).items():
            if info.get("status") == "健康":
                context += f"- {name}：{info.get('role', '')}，{info.get('location', '')}\n"

        context += """
### 最近事件
"""
        for event in state.get("recent_events", [])[-3:]:
            context += f"- {event}\n"

        context += """
### 待回收伏笔
"""
        for thread in state.get("pending_threads", [])[:3]:
            context += f"- {thread.get('thread', '')} (期待章节：{thread.get('expected_chapter', '')})\n"

        context += f"""
### 禁止使用
- 现代词汇：{', '.join(state.get('forbidden_elements', {}).get('modern_terms', [])[:5])}
- 已解决的问题不再重复提及

### 境界体系（重要）
感知者 → 凝聚者 → 外显者 → 领域者 → 大师 → 圣阶
- 主角当前：{state.get('protagonist', {}).get('realm', {}).get('current', '')}
- 格雷当前：感知者中期
"""

        if use_semantic_memory:
            memory_context = self._get_semantic_memory_context(chapter_num, topics)
            if memory_context:
                context += f"""
### 📚 语义记忆（来自前文）
{memory_context}
"""

        return context

    def _init_llm_client(self):
        if OpenAI is None:
            return None
        api_key = self._load_api_key()
        if not api_key:
            return None
        return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    def _load_api_key(self) -> Optional[str]:
        api_path = self.repo_root / "deepseek_api.txt"
        if api_path.exists():
            return api_path.read_text(encoding="utf-8").strip()
        config_path = self.project_path / "config.yaml"
        if config_path.exists():
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            return data.get("models", {}).get("writing", {}).get("api_key")
        return None

    def _get_semantic_memory_context(self, chapter_num: int, topics: Optional[List[str]] = None) -> str:
        try:
            from story_memory_adapter import StoryMemoryAdapter
        except Exception:
            return ""

        adapter = StoryMemoryAdapter(clear_db=False)
        try:
            memory_parts = []
            events = adapter.query_context(
                f"第{chapter_num-5}章到第{chapter_num-1}章的重要事件", max_entries=5
            )
            if events and events != "未找到相关记忆":
                memory_parts.append(f"**前文事件**:\n{events}")

            if topics:
                for topic in topics[:3]:
                    topic_memory = adapter.query_context(topic, max_entries=3)
                    if topic_memory and topic_memory != "未找到相关记忆":
                        memory_parts.append(f"**{topic}相关**:\n{topic_memory}")

            return "\n\n".join(memory_parts)
        except Exception:
            return ""

    def extract_state_changes(self, chapter_num: int, content: str) -> Dict[str, Any]:
        """软状态抽取（原逻辑，使用 LLM）"""
        if not self._llm_client:
            return {}

        prompt = f"""请分析以下第{chapter_num}章的内容，提取需要更新的状态变化。

## 章节内容
{content[:6000]}

## 需要提取的信息
请以JSON格式输出以下变化（如果有的话），没有变化的项留空：

```json
{{
  "realm_change": null,
  "location_change": null,
  "new_characters": [],
  "character_status_changes": {{}},
  "new_skills": [],
  "new_facilities": [],
  "population_change": null,
  "key_events": [],
  "new_threads": [],
  "resolved_threads": [],
  "time_progression": null
}}
```

只输出JSON，不要其他内容：
"""

        try:
            response = self._llm_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是小说状态分析师。精确提取章节中的状态变化，以JSON格式输出。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1500,
                temperature=0.1,
            )
            result_text = response.choices[0].message.content
            json_match = re.search(r"```json\s*([\s\S]*?)\s*```", result_text)
            if json_match:
                return json.loads(json_match.group(1))
            return json.loads(result_text)
        except Exception:
            return {}

    def update_state_after_chapter(self, chapter_num: int, changes: Dict[str, Any]):
        """软状态更新（原逻辑）"""
        if not self.story_state:
            return

        self.story_state.setdefault("meta", {})["current_chapter"] = chapter_num

        if changes.get("realm_change"):
            self.story_state.setdefault("protagonist", {}).setdefault("realm", {})["current"] = changes[
                "realm_change"
            ]
            self.story_state["protagonist"]["realm"]["level"] = "初阶"
            self.story_state["protagonist"]["realm"]["breakthrough_chapter"] = chapter_num

        if changes.get("location_change"):
            self.story_state.setdefault("protagonist", {})["location"] = changes["location_change"]

        for skill in changes.get("new_skills", []):
            self.story_state.setdefault("protagonist", {}).setdefault("skills", []).append(
                {"name": skill, "level": "基础", "source": f"第{chapter_num}章获得"}
            )

        if changes.get("population_change"):
            try:
                self.story_state.setdefault("territory", {}).setdefault("population", 0)
                self.story_state["territory"]["population"] += int(changes["population_change"])
            except Exception:
                pass

        for event in changes.get("key_events", []):
            event_str = f"第{chapter_num}章：{event}"
            self.story_state.setdefault("recent_events", [])
            if event_str not in self.story_state["recent_events"]:
                self.story_state["recent_events"].append(event_str)

        self.story_state["recent_events"] = self.story_state.get("recent_events", [])[-10:]

        for thread in changes.get("new_threads", []):
            self.story_state.setdefault("pending_threads", []).append(
                {"thread": thread, "urgency": "中", "expected_chapter": f"{chapter_num + 5}+"}
            )

        for resolved in changes.get("resolved_threads", []):
            self.story_state["pending_threads"] = [
                t for t in self.story_state.get("pending_threads", []) if resolved.lower() not in t.get("thread", "").lower()
            ]
            self.story_state.setdefault("forbidden_elements", {}).setdefault("resolved_threads", []).append(resolved)

        if changes.get("time_progression"):
            self.story_state.setdefault("meta", {})["story_time"] = (
                self.story_state.get("meta", {}).get("story_time", "") + f" ({changes['time_progression']})"
            )

        for event in changes.get("key_events", [])[:1]:
            self.story_state.setdefault("timeline", []).append(
                {"chapter": chapter_num, "event": event, "time": self.story_state.get("meta", {}).get("story_time")}
            )

        self._save_story_state()

    def check_consistency(self, chapter_num: int, content: str) -> List[str]:
        """软状态一致性检查（原逻辑）"""
        issues = []
        state = self.story_state or {}

        current_realm = state.get("protagonist", {}).get("realm", {}).get("current", "")
        if current_realm:
            wrong_realms = ["凝聚者", "外显者", "领域者", "大师", "圣阶"]
            if current_realm in wrong_realms:
                wrong_realms.remove(current_realm)
            for wrong in wrong_realms:
                if f"艾伦是{wrong}" in content or f"已是{wrong}" in content:
                    if wrong != current_realm:
                        issues.append(f"境界错误：主角当前应为{current_realm}，但内容提及{wrong}")

        for term in state.get("forbidden_elements", {}).get("modern_terms", []):
            if term in content:
                issues.append(f"现代词汇：发现'{term}'")

        for char in state.get("forbidden_elements", {}).get("dead_characters", []):
            if char in content and "回忆" not in content[:500]:
                issues.append(f"角色错误：{char}已死亡，不应出现")

        return issues


# 便捷函数（向后兼容）

def get_writing_context(chapter_num: int) -> str:
    manager = StoryStateManager()
    return manager.generate_context_for_writing(chapter_num)


def update_state_after_writing(chapter_num: int, content: str):
    manager = StoryStateManager()
    changes = manager.extract_state_changes(chapter_num, content)
    if changes:
        manager.update_state_after_chapter(chapter_num, changes)
    return changes


def check_chapter_consistency(chapter_num: int, content: str) -> List[str]:
    manager = StoryStateManager()
    return manager.check_consistency(chapter_num, content)


if __name__ == "__main__":
    manager = StoryStateManager()
    snapshot = manager.get_snapshot(1)
    print(StoryStateManager.format_snapshot_for_prompt(snapshot))

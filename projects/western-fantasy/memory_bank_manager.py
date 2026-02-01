"""Manage memory_bank updates with patch-based writes."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from llm_clients import OpenAICompatibleClient, safe_json_loads
import yaml


@dataclass
class PatchProposal:
    ops: List[Dict[str, Any]]


class MemoryBankManager:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.bank_path = project_path / "memory_bank"
        self.core_path = self.bank_path / "Core"
        self.style_path = self.bank_path / "Style"
        self.patch_dir = project_path / "memory_bank" / "patches"
        self.patch_dir.mkdir(parents=True, exist_ok=True)
        self.canon = self._load_canon()

    def _load_canon(self) -> Dict[str, Any]:
        canon_path = self.project_path / "canon.yaml"
        if canon_path.exists():
            return yaml.safe_load(canon_path.read_text(encoding="utf-8")) or {}
        return {}

    def read_core(self) -> Dict[str, str]:
        contents = {}
        for file in [
            "projectbrief.md",
            "story_structure.md",
            "world_and_characters.md",
            "activeContext.md",
            "progress.md",
        ]:
            path = self.core_path / file
            if path.exists():
                contents[file] = path.read_text(encoding="utf-8")
        return contents

    def update_from_outline(
        self, chapter_num: int, outline_text: str, client: Optional[OpenAICompatibleClient] = None
    ) -> tuple[PatchProposal, PatchProposal]:
        summary = self._simple_summary(outline_text)
        ops = [
            {
                "op": "append",
                "file": "Core/progress.md",
                "content": f"- Chapter {chapter_num} planned: {summary}",
                "evidence": {"quote": summary, "chapter_pos": "outline"},
            }
        ]
        proposal = PatchProposal(ops=ops)
        self._write_patch(proposal, f"outline_{chapter_num:03d}")
        applied = self.validate_patch(proposal)
        self._apply_patch(applied)
        return proposal, applied

    def update_from_chapter(
        self, chapter_num: int, chapter_text: str, client: Optional[OpenAICompatibleClient] = None
    ) -> tuple[PatchProposal, PatchProposal]:
        if client:
            proposal = self._llm_patch_proposal(chapter_num, chapter_text, client)
        else:
            summary = self._simple_summary(chapter_text)
            proposal = PatchProposal(
                ops=[
                    {
                        "op": "append",
                        "file": "Core/progress.md",
                        "content": f"- Chapter {chapter_num} established: {summary}",
                        "evidence": {"quote": summary, "chapter_pos": f"chapter_{chapter_num:03d}"},
                    },
                    {
                        "op": "append",
                        "file": "Core/activeContext.md",
                        "content": f"- Current: Chapter {chapter_num}",
                        "evidence": {"quote": summary, "chapter_pos": f"chapter_{chapter_num:03d}"},
                    },
                ]
            )

        self._write_patch(proposal, f"chapter_{chapter_num:03d}")
        applied = self.validate_patch(proposal)
        self._apply_patch(applied)
        return proposal, applied

    def consistency_audit(self) -> List[str]:
        issues = []
        world_file = self.core_path / "world_and_characters.md"
        if not world_file.exists():
            return issues

        text = world_file.read_text(encoding="utf-8")
        name_to_birth = {}
        for line in text.splitlines():
            if "出生地" in line:
                match = re.match(r"-\s*(.+?)：.*出生地[:：]\s*(.+)$", line)
                if match:
                    name = match.group(1).strip()
                    birthplace = match.group(2).strip()
                    if name in name_to_birth and name_to_birth[name] != birthplace:
                        issues.append(f"{name} 出生地冲突: {name_to_birth[name]} vs {birthplace}")
                    name_to_birth[name] = birthplace
        return issues

    def _apply_patch(self, proposal: PatchProposal):
        for op in proposal.ops:
            if op.get("op") != "append":
                continue
            file_rel = op.get("file")
            content = op.get("content", "").strip()
            if not file_rel or not content:
                continue
            path = self.bank_path / file_rel
            path.parent.mkdir(parents=True, exist_ok=True)
            existing = path.read_text(encoding="utf-8") if path.exists() else ""
            if file_rel == "Core/activeContext.md" and content.startswith("- Current:"):
                lines = [line for line in existing.splitlines() if not line.strip().startswith("- Current:")]
                updated = "\n".join(lines).rstrip() + "\n" + content + "\n"
            else:
                updated = (existing.rstrip() + "\n" + content + "\n").lstrip()
            path.write_text(updated, encoding="utf-8")

    def _write_patch(self, proposal: PatchProposal, name: str):
        path = self.patch_dir / f"memory_patch_{name}.json"
        path.write_text(json.dumps({"ops": proposal.ops}, ensure_ascii=False, indent=2), encoding="utf-8")

    def _llm_patch_proposal(self, chapter_num: int, chapter_text: str, client: OpenAICompatibleClient) -> PatchProposal:
        prompt = f"""根据章节内容，输出 JSON Patch 提案（不直接改写文件）。

目标文件：
- Core/progress.md: 追加一行本章摘要
- Core/activeContext.md: 更新 Current Chapter

输出 JSON 结构：{{"ops": [{{"op": "append", "file": "Core/progress.md", "content": "...", "evidence": {{"quote": "...", "chapter_pos": "..."}}}}, {{"op": "append", "file": "Core/activeContext.md", "content": "...", "evidence": {{"quote": "...", "chapter_pos": "..."}}}}]}}

章节内容（截断）：
{chapter_text[:3000]}
"""
        raw = client.chat(
            [
                {"role": "system", "content": "你是故事资料维护助手，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        data = safe_json_loads(raw)
        return PatchProposal(ops=data.get("ops", []))

    def _simple_summary(self, text: str) -> str:
        sentences = re.split(r"[。！？!?]\s*", text.strip())
        return " / ".join([s for s in sentences if s][:2])[:120]

    def validate_patch(self, proposal: PatchProposal) -> PatchProposal:
        allowed_files = {
            "Core/progress.md",
            "Core/activeContext.md",
            "Core/world_and_characters.md",
            "Core/projectbrief.md",
            "Core/story_structure.md",
        }
        valid_ops: List[Dict[str, Any]] = []
        for op in proposal.ops:
            if op.get("op") != "append":
                continue
            if op.get("file") not in allowed_files:
                continue
            content = (op.get("content") or "").strip()
            evidence = op.get("evidence") or {}
            if not content or not evidence:
                continue
            content = self._normalize_names(content)
            op = dict(op)
            op["content"] = content
            valid_ops.append(op)
        return PatchProposal(ops=valid_ops)

    def _normalize_names(self, text: str) -> str:
        canonical = ""
        aliases: List[str] = []
        for fact in self.canon.get("SOFT_FACT", []):
            if fact.get("key") == "protagonist.canonical_name":
                canonical = fact.get("value", "")
            if fact.get("key") == "protagonist.aliases":
                aliases = fact.get("value", []) or []

        if canonical:
            for alias in aliases:
                if alias and alias in text and canonical not in text:
                    text = text.replace(alias, canonical)
        return text

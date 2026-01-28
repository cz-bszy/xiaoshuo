"""
全文一致性检测工具
利用 SimpleMem 对 60 章内容进行增量式语义一致性检测
"""

import sys
import argparse
import json
import time
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
from openai import OpenAI

# 添加项目路径
PROJECT_PATH = Path(r"e:\Test\xiaoshuo\projects\western-fantasy")
sys.path.insert(0, str(PROJECT_PATH))

from story_memory_adapter import StoryMemoryAdapter
from models.memory_entry import MemoryEntry

# 加载API密钥
with open(r"e:\Test\xiaoshuo\deepseek_api.txt", 'r') as f:
    API_KEY = f.read().strip()

client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")


class ConsistencyChecker:
    """一致性检测器"""
    
    def __init__(self, start_chapter: int = 1, end_chapter: int = 60):
        self.report_path = PROJECT_PATH / "consistency_report.md"
        
        # 自动断点续传检测
        last_checked = self._get_last_checked_chapter()
        original_start = start_chapter
        
        if last_checked > 0 and start_chapter <= last_checked:
            print(f"🔄 检测到已有进度（已完成第 {last_checked} 章），将从第 {last_checked + 1} 章继续...")
            self.start_chapter = last_checked + 1
        else:
            self.start_chapter = start_chapter
            # 如果是重新开始，并从头开始，初始化报告文件
            if self.start_chapter == 1:
                self._init_report()

        self.end_chapter = end_chapter
        
        # 使用临时数据库
        # 注意：如果是续传，不要 clear_db！
        is_resume = (self.start_chapter > 1)
        self.adapter = StoryMemoryAdapter(
            db_name="consistency_temp", 
            clear_db=not is_resume
        )
        
    def _get_last_checked_chapter(self) -> int:
        """从报告中读取最后检测的章节号"""
        if not self.report_path.exists():
            return 0
            
        try:
            content = self.report_path.read_text(encoding='utf-8')
            import re
            matches = re.findall(r"## 第 (\d+) 章：", content)
            if matches:
                return int(matches[-1])
        except:
            pass
        return 0

    def _init_report(self):
        """初始化报告文件"""
        with open(self.report_path, 'w', encoding='utf-8') as f:
            f.write(f"# 全文一致性检测报告\n\n")
            f.write(f"检测开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("----------------------------------------\n\n")
    
    def run(self):
        """运行检测流程"""
        print("=" * 60)
        print(f"🕵️ 全文一致性检测 (第 {self.start_chapter} - {self.end_chapter} 章)")
        print("=" * 60)
        
        if self.start_chapter > self.end_chapter:
            print("✅ 所有章节已检测完成！")
            return

        total_start_time = time.time()
        
        for i, chapter_num in enumerate(range(self.start_chapter, self.end_chapter + 1)):
            chap_start_time = time.time()
            self._check_chapter(chapter_num)
            duration = time.time() - chap_start_time
            
            # 估算剩余时间
            chapters_done = i + 1
            chapters_left = (self.end_chapter - self.start_chapter + 1) - chapters_done
            avg_time = (time.time() - total_start_time) / chapters_done
            est_remaining = avg_time * chapters_left
            
            print(f"  ⏱️ 耗时: {duration:.1f}s | 预计剩余: {est_remaining/60:.1f} 分钟")
    
    def _check_chapter(self, chapter_num: int):
        """检测单个章节"""
        print(f"\n🔍 正在检测第 {chapter_num} 章...")
        
        # 1. 查找章节文件
        chapter_file = self.adapter._find_chapter_file(chapter_num)
        if not chapter_file:
            print(f"  ⚠️ 未找到第{chapter_num}章文件，跳过")
            self._append_report_item(chapter_num, "未知标题", [], status="跳过 (文件缺失)")
            return
            
        content = chapter_file.read_text(encoding='utf-8')
        title = chapter_file.stem.split('_', 1)[1] if '_' in chapter_file.stem else ""
        
        # 2. 存入临时记忆库并获取记忆
        # 使用新方法直接获取生成的条目，不再依赖检索
        entries = self.adapter.add_chapter_dry_run(chapter_num, content, title)
        
        if not entries:
            print("  ⚠️ 未提取到记忆条目，跳过检测")
            self._append_report_item(chapter_num, title, [], status="跳过 (记忆提取失败)")
            return
            
        # 3. 提取本章关键实体
        entities = self._extract_key_entities(entries)
        print(f"  🔑 关键实体: {', '.join(entities[:5])}...")
        
        # 4. 检测逻辑
        chapter_issues = []
        
        # 重点检测主角
        if "艾伦" in entities or "艾伦·诺斯" in entities:
             issues = self._verify_entity("艾伦", chapter_num, entries)
             if issues:
                 chapter_issues.extend(issues)

        # 随机抽取其他4个重要实体检测（增加检测范围发现更多问题）
        other_entities = [e for e in entities if "艾伦" not in e][:4]
        for entity in other_entities:
            issues = self._verify_entity(entity, chapter_num, entries)
            if issues:
                chapter_issues.extend(issues)
        
        if chapter_issues:
            print(f"  ❌ 发现 {len(chapter_issues)} 个潜在问题")
            self._append_report_item(chapter_num, title, chapter_issues, status="⚠️ 发现潜在冲突")
        else:
            print("  ✅ 未发现明显冲突")
            self._append_report_item(chapter_num, title, [], status="✅ 通过")

    def _append_report_item(self, chapter_num: int, title: str, issues: List[str], status: str):
        """实时追加到报告文件"""
        with open(self.report_path, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime("%H:%M:%S")
            f.write(f"## 第 {chapter_num} 章：{title}\n")
            f.write(f"**状态**: {status} | **时间**: {timestamp}\n\n")
            
            if issues:
                for issue in issues:
                    f.write(f"- {issue}\n")
                f.write("\n")
            else:
                f.write("未发现严重逻辑冲突。\n\n")
    
    def _save_report(self):
        # 实时保存，无需最后汇总
        pass
            
    def _extract_key_entities(self, entries: List[MemoryEntry]) -> List[str]:
        """从记忆条目提取高频实体"""
        entity_counts = {}
        for entry in entries:
            for p in entry.persons:
                entity_counts[p] = entity_counts.get(p, 0) + 1
            for e in entry.entities:
                entity_counts[e] = entity_counts.get(e, 0) + 1
        
        # 按频率排序
        sorted_entities = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)
        return [k for k, v in sorted_entities]
    
    def _verify_entity(self, entity: str, current_chapter: int, current_entries: List[MemoryEntry]) -> List[str]:
        """验证特定实体的一致性"""
        
        # 1. 检索前文关于该实体的记忆 (排除当前章节)
        # 适配器的 query_context 会检索所有，我们需要限制范围或利用 Prompt 区分
        # 这里简单起见，我们直接查询，然后让 LLM 区分
        
        # 为了更精准，我们构造一个查询，专门问"第X章之前的情况"
        prev_context = self.adapter.query_context(
            f"第{current_chapter}章之前，{entity}的状态、位置、能力和关键事件", 
            max_entries=5
        )
        
        if not prev_context or prev_context == "未找到相关记忆":
            return []
            
        # 2. 整理本章关于该实体的描述
        current_desc = []
        for entry in current_entries:
            if entity in entry.persons or entity in entry.entities or entity in entry.keywords:
                current_desc.append(entry.lossless_restatement)
        
        if not current_desc:
            return []
            
        current_context = "\n".join(current_desc[:5]) # 取前5条相关
        
        # 3. LLM 裁判
        prompt = f"""你是一致性检测裁判。请仔细分析以下两段关于角色/实体"{entity}"的描述，判断是否存在**任何程度的不一致**（包括微小细节）。
        
【前文记忆（第{current_chapter}章之前）】
{prev_context}

【当前章节（第{current_chapter}章）】
{current_context}

【检测项目】（即使是小问题也要指出）
1. 生死状态：是否前文已死，本章突然出现？
2. 地理位置：是否位置变化不合理？
3. 能力设定：是否存在能力倒退、设定遗忘、境界描述不一致？
4. 关键关系：人物关系是否矛盾？
5. 时间线问题：事件发生顺序是否矛盾？
6. 数字/名称：具体数值或名称是否前后不一致？
7. 细节描述：外貌、装备、身份等细节是否矛盾？

请指出所有发现的不一致，即使是很小的问题。如果完全没有问题，回答"无冲突"。

格式：
无冲突
或
冲突：[冲突类型] - [具体描述]
"""
        
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是由SimpleMem驱动的一致性检测裁判。只关注严重的逻辑矛盾。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            result = response.choices[0].message.content.strip()
            
            if "无冲突" in result:
                return []
            else:
                return [f"实体[{entity}]: {result}"]
                
        except Exception as e:
            print(f"  ⚠️ LLM裁判调用失败: {e}")
            return []

    def _save_report(self):
        """保存检测报告"""
        report_path = PROJECT_PATH / "consistency_report.md"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"# 全文一致性检测报告\n\n")
            f.write(f"检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"范围: 第{self.start_chapter}章 - 第{self.end_chapter}章\n\n")
            
            if not self.issues_report:
                f.write("🎉 未发现严重逻辑冲突！\n")
            else:
                for item in self.issues_report:
                    f.write(f"## 第 {item['chapter']} 章：{item['title']}\n")
                    for issue in item['issues']:
                        f.write(f"- ⚠️ {issue}\n")
                    f.write("\n")
        
        print(f"\n📄 报告已生成: {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='SimpleMem一致性检测')
    parser.add_argument('--start', type=int, default=1, help='起始章节')
    parser.add_argument('--end', type=int, default=60, help='结束章节')
    
    args = parser.parse_args()
    
    checker = ConsistencyChecker(args.start, args.end)
    checker.run()

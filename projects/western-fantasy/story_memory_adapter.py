"""
故事记忆适配器 - SimpleMem 与小说项目的桥梁
负责：章节记忆提取、语义检索、记忆管理
"""

import sys
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

# 添加 SimpleMem 路径
PROJECT_PATH = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_PATH.parents[1]
SIMPLEMEM_PATH = REPO_ROOT / "SimpleMem"
sys.path.insert(0, str(SIMPLEMEM_PATH))

from main import SimpleMemSystem
from models.memory_entry import MemoryEntry

# 项目路径
CHAPTERS_PATH = PROJECT_PATH / "chapters" / "v01"


class StoryMemoryAdapter:
    """
    故事记忆适配器
    
    功能：
    - 将章节内容转换为语义记忆
    - 提供智能上下文检索
    - 管理故事时间线记忆
    """
    
    def __init__(self, clear_db: bool = False, db_name: str = "story_memory"):
        """
        初始化适配器
        
        Args:
            clear_db: 是否清空现有记忆库
            db_name: 数据库名称（用于区分不同项目）
        """
        print("=" * 60)
        print("🧠 初始化故事记忆适配器")
        print("=" * 60)
        
        # 初始化 SimpleMem
        self.memory_system = SimpleMemSystem(
            clear_db=clear_db,
            db_path=str(PROJECT_PATH / "memory_db"),
            table_name=db_name,
            enable_parallel_processing=True,
            max_parallel_workers=4
        )
        
        # 章节记忆统计
        self.chapter_stats: Dict[int, int] = {}  # 章节号 -> 记忆条目数
        
        print("✅ 故事记忆适配器初始化完成")
    
    def add_chapter(self, chapter_num: int, content: str, title: str = "") -> int:
        """
        将章节内容添加到记忆库
        
        Args:
            chapter_num: 章节号
            content: 章节内容
            title: 章节标题
            
        Returns:
            添加的记忆条目数
        """
        print(f"\n📖 处理第{chapter_num}章: {title}")
        
        # 分段处理长文本（每段约2000字）
        segments = self._split_content(content, max_chars=2000)
        
        # 构建对话格式（SimpleMem 期望对话输入）
        story_time = f"第{chapter_num}章"
        
        for i, segment in enumerate(segments):
            # 使用叙述者作为 speaker
            self.memory_system.add_dialogue(
                speaker="叙述者",
                content=f"[{title}] {segment}",
                timestamp=f"第{chapter_num}章-段落{i+1}"
            )
        
        # 处理记忆
        self.memory_system.finalize()
        
        # 记录统计
        self.chapter_stats[chapter_num] = len(segments)
        
        print(f"  ✅ 已添加 {len(segments)} 个记忆片段")
        return len(segments)
    
    def query_context(
        self, 
        question: str, 
        chapter_num: Optional[int] = None,
        max_entries: int = 10
    ) -> str:
        """
        查询相关上下文
        
        Args:
            question: 查询问题（如"艾伦的修炼进度"）
            chapter_num: 可选，限制到某章之前的记忆
            max_entries: 返回的最大条目数
            
        Returns:
            格式化的上下文字符串
        """
        print(f"\n🔍 查询: {question}")
        
        # 使用 SimpleMem 检索
        try:
            # 获取检索结果
            contexts = self.memory_system.hybrid_retriever.retrieve(question)
            
            # 格式化输出
            context_lines = []
            for i, entry in enumerate(contexts[:max_entries]):
                context_lines.append(f"- {entry.lossless_restatement}")
            
            result = "\n".join(context_lines) if context_lines else "未找到相关记忆"
            print(f"  📝 找到 {len(contexts)} 条相关记忆")
            return result
            
        except Exception as e:
            print(f"  ⚠️ 查询失败: {e}")
            return ""
    
    def ask_story(self, question: str) -> str:
        """
        直接问答（返回完整答案）
        
        Args:
            question: 问题
            
        Returns:
            由 LLM 生成的答案
        """
        return self.memory_system.ask(question)
    
    def get_character_history(self, character_name: str) -> str:
        """
        获取角色的历史记录
        
        Args:
            character_name: 角色名（如"艾伦"、"格雷"）
            
        Returns:
            角色相关的记忆摘要
        """
        return self.query_context(f"{character_name}的经历和状态变化")
    
    def get_timeline_events(self, start_chapter: int = 1, end_chapter: int = 60) -> str:
        """
        获取时间线上的关键事件
        
        Args:
            start_chapter: 起始章节
            end_chapter: 结束章节
            
        Returns:
            时间线事件列表
        """
        return self.query_context(
            f"从第{start_chapter}章到第{end_chapter}章发生的重要事件"
        )
    
    def get_writing_context(self, chapter_num: int, topics: List[str] = None) -> str:
        """
        为写作生成相关上下文
        
        Args:
            chapter_num: 要写的章节号
            topics: 本章涉及的主题（可选）
            
        Returns:
            综合的写作上下文
        """
        context_parts = []
        
        # 基础查询：前文概要
        context_parts.append("## 前文关键记忆\n")
        context_parts.append(self.query_context(
            f"第{chapter_num-1}章到第{chapter_num}章之前发生的重要事件"
        ))
        
        # 主角状态
        context_parts.append("\n## 主角当前状态\n")
        context_parts.append(self.query_context("艾伦当前的境界、位置和状态"))
        
        # 如果有特定主题
        if topics:
            context_parts.append("\n## 相关背景\n")
            for topic in topics:
                context_parts.append(f"### {topic}\n")
                context_parts.append(self.query_context(topic))
        
        return "\n".join(context_parts)
    
    def import_all_chapters(self, chapter_range: tuple = (1, 60)) -> Dict[str, Any]:
        """
        批量导入所有章节
        
        Args:
            chapter_range: (起始章节, 结束章节)
            
        Returns:
            导入统计
        """
        start, end = chapter_range
        stats = {
            "total_chapters": 0,
            "total_segments": 0,
            "failed_chapters": []
        }
        
        print(f"\n📚 开始导入第{start}章到第{end}章...")
        print("=" * 60)
        
        for chapter_num in range(start, end + 1):
            # 查找章节文件
            chapter_file = self._find_chapter_file(chapter_num)
            
            if chapter_file:
                try:
                    content = chapter_file.read_text(encoding='utf-8')
                    title = chapter_file.stem.split('_', 1)[1] if '_' in chapter_file.stem else ""
                    
                    segments = self.add_chapter(chapter_num, content, title)
                    stats["total_chapters"] += 1
                    stats["total_segments"] += segments
                    
                except Exception as e:
                    print(f"  ❌ 第{chapter_num}章导入失败: {e}")
                    stats["failed_chapters"].append(chapter_num)
            else:
                print(f"  ⚠️ 未找到第{chapter_num}章文件")
                stats["failed_chapters"].append(chapter_num)
        
        print("\n" + "=" * 60)
        print(f"📊 导入完成: {stats['total_chapters']} 章, {stats['total_segments']} 个记忆片段")
        
        return stats
    
    def _split_content(self, content: str, max_chars: int = 2000) -> List[str]:
        """将长文本分割为段落"""
        # 按段落分割
        paragraphs = content.split('\n\n')
        
        segments = []
        current_segment = ""
        
        for para in paragraphs:
            if len(current_segment) + len(para) <= max_chars:
                current_segment += para + "\n\n"
            else:
                if current_segment:
                    segments.append(current_segment.strip())
                current_segment = para + "\n\n"
        
        if current_segment:
            segments.append(current_segment.strip())
        
        return segments
    
    def _find_chapter_file(self, chapter_num: int) -> Optional[Path]:
        """查找章节文件"""
        for f in CHAPTERS_PATH.glob(f"第{chapter_num}章_*.txt"):
            return f
        return None
    
    def add_chapter_dry_run(self, chapter_num: int, content: str, title: str = "") -> List[MemoryEntry]:
        """
        处理章节并返回记忆条目，同时写入数据库（用于一致性检查）
        """
        print(f"\n📖 [检测模式] 处理第{chapter_num}章: {title}")
        segments = self._split_content(content, max_chars=2000)
        
        all_entries = []
        builder = self.memory_system.memory_builder
        
        # 构造 Dialogue 对象列表
        from models.memory_entry import Dialogue
        
        dialogues = []
        # 计算起始 ID
        start_id = builder.processed_count + len(builder.dialogue_buffer) + 1
        
        for i, segment in enumerate(segments):
            d = Dialogue(
                dialogue_id=start_id + i,
                speaker="叙述者",
                content=f"[{title}] {segment}",
                timestamp=f"第{chapter_num}章"
            )
            dialogues.append(d)
            
        if not dialogues:
            return []
            
        try:
            # 直接调用内部生成逻辑
            print(f"  ⚡ 正在提取记忆 (共 {len(dialogues)} 段)...")
            entries = builder._generate_memory_entries(dialogues)
            
            if entries:
                # 写入数据库，确保后续检索可用
                self.memory_system.vector_store.add_entries(entries)
                # 更新 builder 状态
                builder.previous_entries = entries
                builder.processed_count += len(dialogues)
                
                all_entries.extend(entries)
                print(f"  ✅ 生成 {len(entries)} 条记忆")
            else:
                print("  ⚠️ 未生成任何记忆")
                
        except Exception as e:
            print(f"  ❌ 记忆生成失败: {e}")
            
        return all_entries

    def get_memories_by_chapter(self, chapter_num: int) -> List[MemoryEntry]:
        """
        获取特定章节的所有记忆条目
        
        Args:
            chapter_num: 章节号
            
        Returns:
            记忆条目列表
        """
        # ... (保留原方法以备不时之需)
        # 获取所有记忆
        all_entries = self.memory_system.get_all_memories()
        
        # 过滤出本章的记忆
        chapter_prefix = f"第{chapter_num}章"
        
        chapter_entries = []
        for entry in all_entries:
            if entry.timestamp and entry.timestamp.startswith(chapter_prefix):
                chapter_entries.append(entry)
                
        return chapter_entries

    def print_stats(self):
        """打印统计信息"""
        print("\n📊 记忆库统计")
        print("=" * 40)
        print(f"已处理章节: {len(self.chapter_stats)}")
        print(f"总记忆片段: {sum(self.chapter_stats.values())}")
        
        # 获取所有记忆
        all_memories = self.memory_system.get_all_memories()
        print(f"数据库条目: {len(all_memories)}")


# 便捷函数
def create_story_memory(clear_db: bool = False) -> StoryMemoryAdapter:
    """创建故事记忆适配器实例"""
    return StoryMemoryAdapter(clear_db=clear_db)


def query_story_memory(question: str) -> str:
    """快速查询故事记忆"""
    adapter = StoryMemoryAdapter(clear_db=False)
    return adapter.query_context(question)


if __name__ == "__main__":
    # 测试
    print("🧪 测试故事记忆适配器")
    
    adapter = StoryMemoryAdapter(clear_db=True)
    
    # 测试添加章节
    test_content = """
    艾伦站在破旧的城堡大厅中，目光扫过斑驳的墙壁。这就是诺斯堡，他的领地中心。
    
    塞巴斯站在他身后，老管家的眼中带着复杂的神色。"少爷，这里已经荒废多年了。"
    
    "我知道。"艾伦点点头，"但这正是我们的机会。给我三年时间，我会让这里焕然一新。"
    
    格雷带着巡逻队从外面回来，向艾伦汇报："东边的森林里发现了魔兽的踪迹，看样子是低级的影狼群。"
    """
    
    adapter.add_chapter(1, test_content, "测试章节")
    
    # 测试查询
    result = adapter.query_context("艾伦在诺斯堡做了什么？")
    print(f"\n查询结果:\n{result}")
    
    print("\n✅ 测试完成")

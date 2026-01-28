"""
检查一致性检测进度
通过查询 consistency_temp 数据库中最新的章节记录
"""
import sys
from pathlib import Path
sys.path.insert(0, r"e:\Test\xiaoshuo\projects\western-fantasy")
sys.path.insert(0, r"e:\Test\xiaoshuo\SimpleMem")

from story_memory_adapter import StoryMemoryAdapter

def check_progress():
    print("🔍 检查进度中...")
    try:
        # 连接到临时数据库
        adapter = StoryMemoryAdapter(db_name="consistency_temp", clear_db=False)
        all_entries = adapter.memory_system.get_all_memories()
        
        if not all_entries:
            print("❌ 数据库为空，尚未开始或已清空")
            return

        # 提取章节号
        max_chapter = 0
        chapter_counts = {}
        
        for entry in all_entries:
            # timestamp 格式预计为 "第X章"
            ts = entry.timestamp or ""
            if ts.startswith("第") and "章" in ts:
                try:
                    chap_str = ts.split("章")[0].replace("第", "")
                    chap_num = int(chap_str)
                    max_chapter = max(max_chapter, chap_num)
                    chapter_counts[chap_num] = chapter_counts.get(chap_num, 0) + 1
                except:
                    pass
        
        print(f"📊 当前数据库状态：")
        print(f"   最大章节号: {max_chapter}")
        print(f"   总记忆条目: {len(all_entries)}")
        print(f"   已处理章节: {sorted(chapter_counts.keys())}")
        
    except Exception as e:
        print(f"❌ 查失败: {e}")

if __name__ == "__main__":
    check_progress()
